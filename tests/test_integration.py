import json
import os
import socket
import sys
import tempfile
import time
import unittest
from pathlib import Path
import psutil

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from fastapi.testclient import TestClient
from engine import Engine, powershell
from main import create_app
from auth_helper import sign_in


class Integration(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(prefix='stackpad-test-')
        self.root = Path(self.folder.name)
        self.app = create_app(self.root, self.root)
        self.client = TestClient(self.app, base_url='http://127.0.0.1:48731', client=('127.0.0.1', 35000))
        self.client.__enter__()
        self.client.headers['origin'] = 'http://127.0.0.1:48731'
        self.engine = self.app.state.engine
        self.ids = []

    def tearDown(self):
        for service_id in self.ids:
            self.engine.stop(service_id)
        self.client.__exit__(None, None, None)
        self.engine.monitor.join(timeout=5)
        self.folder.cleanup()

    def setup_auth(self):
        sign_in(self.app, self.client)

    def add(self, **changes):
        with socket.socket() as probe:
            probe.bind(('127.0.0.1', 0))
            port = probe.getsockname()[1]
        values = dict(name='테스트 API', command=f'"{sys.executable}" -u -m http.server {port} --bind 127.0.0.1', cwd=str(self.root), port=port, health_url=f'http://127.0.0.1:{port}/', color='#22c55e', autostart=False, slot=0)
        values.update(changes)
        result = self.client.post('/api/services', json=values)
        self.assertEqual(result.status_code, 200, result.text)
        service_id = result.json()['id']
        self.ids.append(service_id)
        return service_id, values

    def wait_status(self, expected, timeout=15):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            service = self.client.get('/api/services').json()['services'][0]
            if service['status'] == expected:
                return service
            time.sleep(0.3)
        self.fail(f'Expected {expected}; got {service}')

    def test_auth_and_csrf(self):
        self.assertEqual(self.client.get('/api/services').status_code, 401)
        self.assertFalse(self.client.get('/api/auth').json()['authenticated'])
        self.setup_auth()
        self.assertTrue(self.client.get('/api/auth').json()['authenticated'])
        self.client.headers['origin'] = 'https://evil.example'
        self.assertEqual(self.client.post('/api/logout').status_code, 403)
        self.client.headers['origin'] = 'http://127.0.0.1:48731'
        self.assertEqual(self.client.post('/api/logout').status_code, 200)
        self.assertEqual(self.client.get('/api/services').status_code, 401)

    def test_process_lifecycle_and_recovery(self):
        self.setup_auth()
        service_id, values = self.add()
        self.assertEqual(self.client.post(f'/api/services/{service_id}/start').status_code, 200)
        running = self.wait_status('running')
        self.assertIsNotNone(running['pid'])
        self.assertEqual(self.client.post(f'/api/services/{service_id}/start').status_code, 409)
        self.assertEqual(self.client.put(f'/api/services/{service_id}', json=values).status_code, 409)
        self.assertEqual(self.client.delete(f'/api/services/{service_id}').status_code, 409)
        recovered = Engine(self.root)
        self.assertEqual(recovered.snapshot()[0]['pid'], running['pid'])
        log = self.client.get(f'/api/services/{service_id}/logs').json()['text']
        self.assertIn('Serving HTTP', log)
        self.assertEqual(self.client.post(f'/api/services/{service_id}/stop').status_code, 200)
        self.wait_status('stopped')
        with socket.socket() as probe:
            self.assertNotEqual(probe.connect_ex(('127.0.0.1', values['port'])), 0)
        self.assertEqual(self.client.put(f'/api/services/{service_id}', json={**values, 'name': '수정됨'}).status_code, 200)
        self.assertEqual(self.client.delete(f'/api/services/{service_id}').status_code, 200)
        self.ids.remove(service_id)

    def test_validation_conflict_and_failed_command(self):
        self.setup_auth()
        service_id, values = self.add(command='stackpad_command_that_does_not_exist')
        self.assertEqual(self.client.post('/api/services', json=values).status_code, 409)
        self.assertEqual(self.client.post('/api/services', json={**values, 'slot': 1, 'health_url': 'https://example.com'}).status_code, 422)
        self.assertEqual(self.client.post('/api/services', json={**values, 'slot': 1, 'cwd': 'Z:\\not-a-folder'}).status_code, 422)
        with socket.socket() as occupied:
            occupied.bind(('127.0.0.1', values['port']))
            occupied.listen()
            self.assertEqual(self.client.post(f'/api/services/{service_id}/start').status_code, 409)
        self.assertEqual(self.client.post(f'/api/services/{service_id}/start').status_code, 200)
        self.wait_status('error')
        self.assertIn('stackpad_command_that_does_not_exist', self.engine.tail(service_id))

    def test_autostart_shortcut_and_service(self):
        self.setup_auth()
        original = Engine.startup_path
        Engine.startup_path = property(lambda engine: engine.data_dir / 'startup-test.lnk')
        try:
            self.assertEqual(self.client.put('/api/settings/autostart', json={'enabled': True}).status_code, 200)
            self.assertTrue(self.engine.startup_path.exists())
            escaped = str(self.engine.startup_path).replace("'", "''")
            target = powershell(f"$s=New-Object -ComObject WScript.Shell; $l=$s.CreateShortcut('{escaped}'); $l.TargetPath")
            self.assertTrue(target.endswith('pythonw.exe'), target)
            self.assertEqual(self.client.put('/api/settings/autostart', json={'enabled': False}).status_code, 200)
            self.assertFalse(self.engine.startup_path.exists())
        finally:
            Engine.startup_path = original
        service_id, _ = self.add(autostart=True)
        # A newly opened engine reads persisted config and starts designated services.
        self.client.__exit__(None, None, None)
        self.engine.monitor.join(timeout=5)
        self.app = create_app(self.root, self.root)
        self.engine = self.app.state.engine
        self.client = TestClient(self.app, base_url='http://127.0.0.1:48731', client=('127.0.0.1', 35000))
        self.client.__enter__()
        self.client.headers['origin'] = 'http://127.0.0.1:48731'
        sign_in(self.app, self.client)
        self.wait_status('running')

    def test_pid_reuse_guard(self):
        self.setup_auth()
        service_id, _ = self.add()
        service = self.engine.service(service_id)
        service['runtime'] = {'pid': os.getpid(), 'created': 0}
        self.assertIsNone(self.engine.owned(service))
        self.engine.stop(service_id)
        self.assertTrue(psutil.pid_exists(os.getpid()))

    def test_remote_https_session(self):
        self.setup_auth()
        remote = TestClient(self.app, base_url='https://deck.example', client=('203.0.113.10', 35000))
        remote.headers['origin'] = 'https://deck.example'
        self.assertFalse(remote.get('/api/auth').json()['local'])
        sign_in(self.app, remote)
        self.assertEqual(remote.get('/api/services').status_code, 200)
        service_id, _ = self.add()
        self.assertEqual(remote.post(f'/api/services/{service_id}/start').status_code, 200)
        self.wait_status('running')
        self.assertEqual(remote.post(f'/api/services/{service_id}/stop').status_code, 200)


if __name__ == '__main__':
    unittest.main(verbosity=2)
