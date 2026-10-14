import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from fastapi.testclient import TestClient
from engine import port_open
from main import create_app
from auth_helper import sign_in
from recommend import command_of


def free_port():
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        return probe.getsockname()[1]


class Recommendations(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(prefix='stackpad-recommend-')
        self.root = Path(self.folder.name)
        self.projects = self.root / 'projects'
        self.project = self.projects / 'Alpha' / 'backend'
        self.outside = self.root / 'outside'
        self.project.mkdir(parents=True)
        self.outside.mkdir()
        self.app = create_app(self.root / 'data', self.root)
        self.client = TestClient(self.app, base_url='http://127.0.0.1:48731', client=('127.0.0.1', 35000))
        self.client.__enter__()
        self.client.headers['origin'] = 'http://127.0.0.1:48731'
        self.engine = self.app.state.engine
        self.spawned = []
        sign_in(self.app, self.client)
        result = self.client.put('/api/settings/recommend', json={'roots': [str(self.projects)]})
        self.assertEqual(result.status_code, 200, result.text)

    def tearDown(self):
        for process in self.spawned:
            subprocess.run(['taskkill.exe', '/F', '/T', '/PID', str(process.pid)], stdin=subprocess.DEVNULL, capture_output=True)
        self.client.__exit__(None, None, None)
        self.engine.monitor.join(timeout=5)
        self.folder.cleanup()

    def spawn(self, port, cwd):
        process = subprocess.Popen(f'cmd.exe /d /s /c ""{sys.executable}" -u -m http.server {port} --bind 127.0.0.1"', cwd=cwd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=0x08000000)
        self.spawned.append(process)
        deadline = time.monotonic() + 15
        while not port_open(port):
            self.assertLess(time.monotonic(), deadline, 'Server did not listen')
            time.sleep(0.2)
        return process

    def candidates(self):
        result = self.client.get('/api/recommendations')
        self.assertEqual(result.status_code, 200, result.text)
        return result.json()['candidates']

    def test_project_server_is_suggested_once_and_can_be_hidden(self):
        port = free_port()
        launcher = self.spawn(port, self.project)
        self.spawn(free_port(), self.outside)
        found = [c for c in self.candidates() if c['port'] == port]
        self.assertEqual(len(found), 1)
        candidate = found[0]
        self.assertEqual(candidate['pid'], launcher.pid)
        self.assertEqual(Path(candidate['cwd']), self.project)
        self.assertEqual(candidate['name'], 'Alpha backend')
        self.assertIn(f'http.server {port}', candidate['command'])
        self.assertFalse(candidate['command'].lower().startswith('cmd'))
        self.assertEqual(candidate['health_url'], '', 'Unknown servers are checked by port')
        self.assertEqual(len(self.candidates()), 1, 'Servers outside the scan folders are not suggested')
        details = {k: candidate[k] for k in ('key', 'name', 'cwd', 'command')}
        self.assertEqual(self.client.post('/api/recommendations/hidden', json=details).status_code, 200)
        self.assertEqual(self.candidates(), [])
        self.assertEqual(self.client.get('/api/settings').json()['recommend_hidden'], [details])
        self.assertEqual(self.client.post('/api/recommendations/unhide', json={'key': candidate['key']}).status_code, 200)
        self.assertEqual(len(self.candidates()), 1)
        self.assertEqual(self.client.get('/api/settings').json()['recommend_hidden'], [])
        self.assertEqual(self.client.post('/api/recommendations/unhide', json={'key': candidate['key']}).status_code, 404)
        self.assertEqual(self.client.post('/api/recommendations/hidden', json={'key': candidate['key']}).status_code, 200)
        self.assertEqual(self.client.delete('/api/recommendations/hidden').status_code, 200)
        self.assertEqual(len(self.candidates()), 1)

    def test_hidden_keys_saved_before_details_are_listed_and_restorable(self):
        key = r'c:\users\me\projects\notesdesktop|C:\Users\me\projects\NotesDesktop\.venv\Scripts\pythonw.exe main.py'
        self.engine.config.setdefault('recommend', {})['hidden'] = [key]
        listed = self.client.get('/api/settings').json()['recommend_hidden']
        self.assertEqual(listed, [{'key': key, 'name': 'notesdesktop', 'cwd': r'c:\users\me\projects\notesdesktop', 'command': r'C:\Users\me\projects\NotesDesktop\.venv\Scripts\pythonw.exe main.py'}])
        self.assertEqual(self.client.post('/api/recommendations/unhide', json={'key': key}).status_code, 200)
        self.assertEqual(self.engine.config['recommend']['hidden'], [])

    def test_registered_port_is_not_suggested(self):
        port = free_port()
        self.spawn(port, self.project)
        values = dict(name='Alpha', command='echo registered', cwd=str(self.project), port=port, health_url='', color='#22c55e', autostart=False, slot=0)
        self.assertEqual(self.client.post('/api/services', json=values).status_code, 200)
        self.assertEqual(self.candidates(), [])

    def test_scan_roots_are_validated_and_reported(self):
        self.assertEqual(self.client.put('/api/settings/recommend', json={'roots': [str(self.root / 'missing')]}).status_code, 409)
        self.assertEqual(self.client.put('/api/settings/recommend', json={'roots': ['relative']}).status_code, 409)
        saved = self.client.put('/api/settings/recommend', json={'roots': [str(self.projects), str(self.projects) + '\\', str(self.outside)]}).json()['roots']
        self.assertEqual([Path(r) for r in saved], [self.projects, self.outside])
        self.assertEqual([Path(r) for r in self.client.get('/api/settings').json()['recommend_roots']], [self.projects, self.outside])

    def test_npm_launch_is_suggested_as_npm_command(self):
        npm = SimpleNamespace(name=lambda: 'node.exe', cmdline=lambda: [r'C:\nodejs\node.exe', r'C:\nodejs\node_modules\npm\bin\npm-cli.js', 'run', 'dev'])
        self.assertEqual(command_of(npm), 'npm run dev')
        shell = SimpleNamespace(name=lambda: 'cmd.exe', cmdline=lambda: ['cmd.exe', '/d', '/s', '/c', 'npm run dev'])
        self.assertEqual(command_of(shell), 'npm run dev')


if __name__ == '__main__':
    unittest.main()
