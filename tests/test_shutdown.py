import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from main import create_app
from auth_helper import sign_in


class ShutdownTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.app = create_app(self.folder.name, self.folder.name, control_token='tray-token')
        self.client = TestClient(self.app, base_url='http://127.0.0.1:48731', client=('127.0.0.1', 50000))

    def test_tray_token_shuts_down_and_can_stop_services(self):
        with patch('main.threading.Timer') as timer, patch.object(self.app.state.engine, 'stop_all_local', return_value=[]) as stop_all:
            response = self.client.post('/api/engine/shutdown', json={'stop_services': True}, headers={'X-StackPad-Control': 'tray-token'})
            self.assertEqual(response.status_code, 200, response.text)
            stop_all.assert_called_once()
            timer.return_value.start.assert_called_once()
            self.assertEqual(self.client.post('/api/engine/shutdown', json={}, headers={'X-StackPad-Control': 'tray-token'}).status_code, 200)
            self.assertEqual(stop_all.call_count, 1)

    def test_session_or_wrong_token_cannot_shut_down(self):
        sign_in(self.app, self.client)
        with patch('main.threading.Timer') as timer:
            self.assertEqual(self.client.post('/api/engine/shutdown', json={}, headers={'Origin': 'http://127.0.0.1:48731'}).status_code, 403)
            self.assertEqual(self.client.post('/api/engine/shutdown', json={}, headers={'X-StackPad-Control': 'wrong'}).status_code, 403)
            remote = TestClient(self.app, base_url='https://pc.example.ts.net', client=('127.0.0.1', 50001), headers={'X-Forwarded-For': '100.64.0.2'})
            self.assertEqual(remote.post('/api/engine/shutdown', json={}, headers={'X-StackPad-Control': 'tray-token'}).status_code, 403)
            timer.assert_not_called()

    def test_settings_report_optional_tools(self):
        sign_in(self.app, self.client)
        with patch('main.vscode_path', return_value=None), patch('main.shutil.which', return_value='C:/docker.exe'):
            self.assertEqual(self.client.get('/api/settings').json()['tools'], {'vscode': False, 'docker': True})


if __name__ == '__main__':
    unittest.main()
