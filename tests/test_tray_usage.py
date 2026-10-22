import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from main import create_app


class TrayUsageTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.app = create_app(folder.name, folder.name, control_token='tray-test-token')
        self.client = TestClient(self.app, base_url='http://127.0.0.1:48731', client=('127.0.0.1', 50000))

    def test_tray_reads_enabled_usage_without_browser_login(self):
        self.app.state.engine.config['usage_providers'] = ['codex']
        providers = [{'id': 'codex', 'name': 'Codex', 'status': 'ok', 'windows': []}]
        with patch('main.collect_usage', return_value=providers) as collect:
            response = self.client.get('/api/desktop/usage', headers={'X-StackPad-Control': 'tray-test-token'})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json(), {'providers': providers, 'enabled': ['codex']})
            collect.assert_called_once_with(refresh=False, enabled=['codex'])
            self.assertEqual(self.client.get('/api/usage').status_code, 401)

    def test_rejects_missing_wrong_remote_and_forwarded_credentials(self):
        with patch('main.collect_usage') as collect:
            for token in ('', 'wrong'):
                self.assertEqual(self.client.get('/api/desktop/usage', headers={'X-StackPad-Control': token}).status_code, 403)
            for host, client, extra in (
                ('https://pc.example.ts.net', ('127.0.0.1', 50001), {}),
                ('http://127.0.0.1:48731', ('100.64.0.2', 50001), {}),
                ('http://127.0.0.1:48731', ('127.0.0.1', 50001), {'X-Forwarded-For': '100.64.0.2'}),
            ):
                remote = TestClient(self.app, base_url=host, client=client)
                self.assertEqual(remote.get('/api/desktop/usage', headers={'X-StackPad-Control': 'tray-test-token', **extra}).status_code, 403)
            collect.assert_not_called()

    def test_tray_reads_tailscale_address_with_control_token(self):
        headers = {'X-StackPad-Control': 'tray-test-token'}
        self.assertEqual(self.client.get('/api/desktop/info', headers=headers).json(), {'external_url': None})
        self.app.state.google.save_external_url('https://pc.example.ts.net')
        self.assertEqual(self.client.get('/api/desktop/info', headers=headers).json(), {'external_url': 'https://pc.example.ts.net'})
        self.assertEqual(self.client.get('/api/desktop/info', headers={'X-StackPad-Control': 'wrong'}).status_code, 403)
        remote = TestClient(self.app, base_url='https://pc.example.ts.net', client=('127.0.0.1', 50001))
        self.assertEqual(remote.get('/api/desktop/info', headers=headers).status_code, 403)
