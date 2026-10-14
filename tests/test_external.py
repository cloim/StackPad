import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace

import psutil

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from fastapi.testclient import TestClient
from engine import launcher_only, port_open
from main import create_app
from auth_helper import sign_in


def free_port():
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        return probe.getsockname()[1]


class ExternalLaunch(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(prefix='stackpad-external-')
        self.root = Path(self.folder.name)
        self.project = self.root / 'project'
        self.other = self.root / 'other'
        self.project.mkdir()
        self.other.mkdir()
        self.app = create_app(self.root / 'data', self.root)
        self.client = TestClient(self.app, base_url='http://127.0.0.1:48731', client=('127.0.0.1', 35000))
        self.client.__enter__()
        self.client.headers['origin'] = 'http://127.0.0.1:48731'
        self.engine = self.app.state.engine
        self.ids = []
        self.spawned = []
        sign_in(self.app, self.client)

    def tearDown(self):
        for service_id in self.ids:
            self.engine.stop(service_id)
        for process in self.spawned:
            subprocess.run(['taskkill.exe', '/F', '/T', '/PID', str(process.pid)], stdin=subprocess.DEVNULL, capture_output=True)
        self.client.__exit__(None, None, None)
        self.engine.monitor.join(timeout=5)
        self.folder.cleanup()

    def add(self, port):
        values = dict(name='외부 실행', command=f'"{sys.executable}" -u -m http.server {port} --bind 127.0.0.1', cwd=str(self.project), port=port, health_url=f'http://127.0.0.1:{port}/', color='#22c55e', autostart=False, slot=0)
        result = self.client.post('/api/services', json=values)
        self.assertEqual(result.status_code, 200, result.text)
        self.ids.append(result.json()['id'])
        return self.ids[-1]

    def spawn(self, port, cwd):
        # A shell running one command, like a VS Code task or npm script.
        process = subprocess.Popen(f'cmd.exe /d /s /c ""{sys.executable}" -u -m http.server {port} --bind 127.0.0.1"', cwd=cwd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=0x08000000)
        self.spawned.append(process)
        deadline = time.monotonic() + 15
        while not port_open(port):
            self.assertLess(time.monotonic(), deadline, 'External server did not listen')
            time.sleep(0.2)
        return process

    def service(self):
        return self.client.get('/api/services').json()['services'][0]

    def wait_status(self, expected, timeout=15):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            current = self.service()
            if current['status'] == expected:
                return current
            time.sleep(0.3)
        self.fail(f'Expected {expected}; got {current}')

    def test_project_launch_is_shown_and_taken_over(self):
        port = free_port()
        service_id = self.add(port)
        launcher = self.spawn(port, self.project)
        current = self.wait_status('external')
        self.assertIsNone(current['pid'])
        self.assertTrue(current['external_pid'])
        refused = self.client.post(f'/api/services/{service_id}/start')
        self.assertGreaterEqual(refused.status_code, 400)
        self.assertIsNone(launcher.poll())
        result = self.client.post(f'/api/services/{service_id}/start?takeover=true')
        self.assertEqual(result.status_code, 200, result.text)
        launcher.wait(timeout=10)
        self.assertFalse(psutil.pid_exists(current['external_pid']) and psutil.Process(current['external_pid']).is_running())
        running = self.wait_status('running')
        self.assertIsNone(running['external_pid'])
        owned = self.engine.owned(self.engine.service(service_id))
        self.assertIn(running['pid'], {owned.pid})

    def test_unrelated_listener_is_conflict_and_preserved(self):
        port = free_port()
        service_id = self.add(port)
        launcher = self.spawn(port, self.other)
        self.wait_status('conflict')
        result = self.client.post(f'/api/services/{service_id}/start?takeover=true')
        self.assertGreaterEqual(result.status_code, 400)
        self.assertIsNone(launcher.poll())
        self.assertTrue(port_open(port))

    def test_group_start_takes_over_member(self):
        port = free_port()
        first = self.add(port)
        second_port = free_port()
        values = dict(name='둘째', command=f'"{sys.executable}" -u -m http.server {second_port} --bind 127.0.0.1', cwd=str(self.project), port=second_port, health_url='', color='#22c55e', autostart=False, slot=1)
        second = self.client.post('/api/services', json=values).json()['id']
        self.ids.append(second)
        group = self.client.post('/api/groups', json={'name': '묶음', 'member_ids': [first, second], 'slot': 0}).json()['id']
        launcher = self.spawn(port, self.project)
        self.wait_status('external')
        result = self.client.post(f'/api/groups/{group}/start?takeover=true')
        self.assertEqual(result.status_code, 200, result.text)
        launcher.wait(timeout=10)
        self.assertTrue(all(self.engine.owned(self.engine.service(sid)) for sid in (first, second)))

    def test_interactive_shells_are_not_server_launchers(self):
        shell = lambda *args: SimpleNamespace(cmdline=lambda: ['pwsh.exe', *args])
        self.assertTrue(launcher_only(shell('-NoProfile', '-File', 'run.ps1')))
        self.assertTrue(launcher_only(SimpleNamespace(cmdline=lambda: ['cmd.exe', '/d', '/c', 'npm run dev'])))
        self.assertFalse(launcher_only(shell('-NoLogo')))
        self.assertFalse(launcher_only(shell('-NoExit', '-Command', '. shellIntegration.ps1')))
        self.assertFalse(launcher_only(SimpleNamespace(cmdline=lambda: ['cmd.exe', '/k', 'echo'])))


if __name__ == '__main__':
    unittest.main()
