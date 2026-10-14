import sys
import json
import time
import uuid
import base64
import re
import logging
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from engine import Engine, ServiceInput
from padsets import PadsetInput
from session_store import SessionStore
from storage_location import StorageLocation, resolve_data_dir
from fastapi.testclient import TestClient
import main
from auth_helper import sign_in
import folder_picker
import psutil


class PadsetOrderTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.engine = Engine(self.directory.name)
        self.second = self.engine.save_padset(PadsetInput(name='개발'))
        self.third = self.engine.save_padset(PadsetInput(name='운영'))

    def test_order_persists_after_reopen_and_preserves_names(self):
        ids = [self.third, 'default', self.second]
        self.engine.reorder_padsets(ids)
        restored = Engine(self.directory.name)
        self.assertEqual([s['id'] for s in restored.config['padsets']], ids)
        self.assertEqual([s['name'] for s in restored.config['padsets']], ['운영', '기본', '개발'])

    def test_invalid_orders_leave_config_unchanged(self):
        before = self.engine.config['padsets'][:]
        for ids in ([], ['default'], ['default', self.second, self.second], ['default', self.second, 'missing']):
            with self.assertRaises(ValueError):
                self.engine.reorder_padsets(ids)
            self.assertEqual(self.engine.config['padsets'], before)

    def test_save_failure_rolls_order_back(self):
        before = self.engine.config['padsets'][:]
        with patch.object(self.engine, 'save', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                self.engine.reorder_padsets([self.third, self.second, 'default'])
        self.assertEqual(self.engine.config['padsets'], before)


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'source'
        self.target = self.root / '새 저장 폴더'
        self.target.mkdir()
        self.engine = Engine(self.source)
        self.sessions = SessionStore(self.source)
        self.sessions.create('fixture-session', 'owner@example.com')
        self.pointer = self.source / 'storage-location.json'
        self.storage = StorageLocation(self.engine, self.sessions, self.pointer)

    def test_copy_and_restart_preserve_configuration_sessions_and_logs(self):
        self.engine.save_padset(PadsetInput(name='운영'))
        self.engine.reorder_padsets([self.engine.config['padsets'][1]['id'], 'default'])
        (self.engine.logs / 'history.log').write_text('기존 로그', 'utf-8')
        (self.source / 'custom-fixture.json').write_text('{"fixture": true}', 'utf-8')
        before = self.engine.path.read_bytes()
        self.storage.change(self.target)
        self.assertEqual(self.engine.path.read_bytes(), before)
        self.assertEqual((self.source / 'config.json').read_bytes(), before)
        self.assertEqual((self.target / 'logs/history.log').read_text('utf-8'), '기존 로그')
        self.assertTrue((self.target / 'custom-fixture.json').exists())
        self.assertEqual(resolve_data_dir(self.source), self.target.resolve())
        restored = Engine(resolve_data_dir(self.source))
        self.assertEqual(restored.config, self.engine.config)
        self.assertIsNotNone(SessionStore(self.target).get('fixture-session'))
        self.sessions.create('second-session', 'owner@example.com')
        self.assertIsNotNone(SessionStore(self.target).get('second-session'))
        self.assertIsNone(SessionStore(self.source).get('second-session'))

    def test_same_directory_is_noop_and_nonempty_or_nested_rejected(self):
        self.assertEqual(self.storage.change(self.source), str(self.source.resolve()))
        (self.target / 'keep.txt').write_text('preserve', 'utf-8')
        for destination in [self.target, self.source / 'logs', self.root]:
            with self.assertRaises(ValueError):
                self.storage.change(destination)
        self.assertEqual((self.target / 'keep.txt').read_text('utf-8'), 'preserve')
        self.assertEqual(self.engine.data_dir, self.source)
        self.assertFalse(self.pointer.exists())

    def test_copy_failure_preserves_active_paths_and_pointer(self):
        with patch('storage_location.shutil.copytree', side_effect=OSError('disk full')):
            with self.assertRaises(ValueError):
                self.storage.change(self.target)
        self.assertEqual(self.engine.data_dir, self.source)
        self.assertEqual(self.sessions.path, self.source / 'sessions.json')
        self.assertFalse(self.pointer.exists())

    def test_pointer_write_failure_preserves_active_paths(self):
        self.storage.pointer = self.root / 'missing-parent/location.json'
        with self.assertRaises(ValueError):
            self.storage.change(self.target)
        self.assertEqual(self.engine.data_dir, self.source)
        self.assertEqual(self.sessions.path, self.source / 'sessions.json')

    def test_engine_output_and_logging_handlers_switch_immediately(self):
        old = (self.source / 'engine.log').open('a', encoding='utf-8', buffering=1)
        logger = logging.getLogger('storage-location-fixture')
        handler = logging.StreamHandler(old)
        logger.addHandler(handler)
        try:
            with patch('sys.stderr', old), patch('sys.stdout', old):
                self.storage.change(self.target)
                self.assertIs(sys.stdout, sys.stderr)
                self.assertIs(handler.stream, sys.stderr)
                self.assertTrue(old.closed)
                print('new output', flush=True)
                logger.warning('new logging')
                sys.stderr.close()
            content = (self.target / 'engine.log').read_text('utf-8')
            self.assertIn('new output', content)
            self.assertIn('new logging', content)
        finally:
            logger.removeHandler(handler)
            old.close()

    def test_live_service_logs_continue_after_multiple_moves_and_engine_reopen(self):
        command = f'"{sys.executable}" -u -c "import time; exec(\'while True: print(time.time(), flush=True); time.sleep(0.1)\')"'
        service_id = self.engine.add(ServiceInput(name='log fixture', command=command, cwd=str(self.root), slot=0))
        self.addCleanup(lambda: self.engine.stop(service_id))
        self.engine.start(service_id)
        original_process = self.engine.owned(self.engine.service(service_id))
        self.assertIsNotNone(original_process)
        time.sleep(.4)
        self.storage.change(self.target)
        before = len(self.engine.tail(service_id))
        time.sleep(.4)
        self.assertGreater(len(self.engine.tail(service_id)), before)
        self.assertEqual(self.engine.owned(self.engine.service(service_id)).pid, original_process.pid)
        second = self.root / 'second'
        second.mkdir()
        self.storage.change(second)
        restored = Engine(resolve_data_dir(self.source))
        before = len(restored.tail(service_id))
        time.sleep(.4)
        self.assertGreater(len(restored.tail(service_id)), before)
        self.engine.stop(service_id)
        source_log = Engine(self.source).latest_service_log(service_id) or (self.source / f'logs/{service_id}.log')
        second_log = Engine(second).latest_service_log(service_id) or (second / f'logs/{service_id}.log')
        self.assertEqual(source_log.read_bytes(), second_log.read_bytes())


class StorageApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.source = Path(self.temp.name) / 'source'
        self.target = Path(self.temp.name) / 'target'
        self.target.mkdir()
        self.app = main.create_app(self.source, self.source)
        self.client = TestClient(self.app, base_url='http://127.0.0.1:48731', client=('127.0.0.1', 12345))
        self.addCleanup(self.client.close)
        self.client.headers['origin'] = 'http://127.0.0.1:48731'
        sign_in(self.app, self.client)

    def test_apply_keeps_login_and_new_engine_accepts_existing_cookie(self):
        with patch('main.select_folder', return_value=str(self.target)) as chooser:
            response = self.client.post('/api/settings/data-directory')
        self.assertEqual(response.status_code, 200)
        chooser.assert_called_once_with(self.source)
        self.assertEqual(self.client.get('/api/settings').json()['data_dir'], str(self.target))
        other = TestClient(main.create_app(resolve_data_dir(self.source), self.source), base_url='http://127.0.0.1:48731', client=('127.0.0.1', 12345))
        with other:
            other.cookies.update(self.client.cookies)
            self.assertEqual(other.get('/api/settings').status_code, 200)

    def test_cancel_and_error_leave_location_and_release_dialog_lock(self):
        with patch('main.select_folder', side_effect=[None, ValueError('fixture'), None]):
            self.assertTrue(self.client.post('/api/settings/data-directory').json()['cancelled'])
            self.assertEqual(self.client.post('/api/settings/data-directory').status_code, 409)
            self.assertTrue(self.client.post('/api/settings/data-directory').json()['cancelled'])
        self.assertEqual(self.app.state.engine.data_dir, self.source)

    def test_forwarded_requests_cannot_open_local_dialog(self):
        with patch('main.select_folder') as chooser:
            response = self.client.post('/api/settings/data-directory', headers={'x-forwarded-for': '192.0.2.1'})
            self.assertEqual(response.status_code, 403)
            chooser.assert_not_called()
        self.assertFalse(self.client.get('/api/settings', headers={'x-forwarded-for': '192.0.2.1'}).json()['can_select_data_dir'])

    def test_concurrent_dialog_and_unsigned_requests_are_rejected(self):
        lock = self.app.state.storage_location.selection_lock
        lock.acquire()
        try:
            with patch('main.select_folder') as chooser:
                self.assertEqual(self.client.post('/api/settings/data-directory').status_code, 409)
                chooser.assert_not_called()
        finally:
            lock.release()
        self.client.cookies.clear()
        with patch('main.select_folder') as chooser:
            self.assertEqual(self.client.post('/api/settings/data-directory').status_code, 401)
            chooser.assert_not_called()


class FolderPickerTests(unittest.TestCase):
    def test_sta_dialog_selection_and_cancel_even_if_child_already_exited(self):
        for selection in [None, 'C:\\새 폴더']:
            def launch(script):
                encoded = re.search(r'-EncodedCommand ([A-Za-z0-9+/=]+)', script).group(1)
                dialog = base64.b64decode(encoded).decode('utf-16-le')
                self.assertIn('-STA', script)
                self.assertIn('FolderBrowserDialog', dialog)
                output = re.search(r"\[IO.File\]::Move\('[^']*', '([^']+)'\)", dialog).group(1)
                Path(output).write_text(json.dumps({'path': selection}, ensure_ascii=False), 'utf-8')
                return '{"ReturnValue":0,"ProcessId":12345}'
            with patch('engine.powershell', side_effect=launch), patch('folder_picker.psutil.Process', side_effect=psutil.NoSuchProcess(12345)):
                self.assertEqual(folder_picker.select_folder(Path('C:/현재 폴더')), selection)
