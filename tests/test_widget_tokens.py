import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from main import create_app
from auth_helper import sign_in

PROVIDERS = [{'id': 'claude', 'name': 'Claude', 'status': 'ok', 'plan': None, 'windows': [], 'message': None, 'fetched_at': '2026-10-13T00:00:00+00:00'}]


class WidgetTokenTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.data = Path(self.folder.name)
        self.base = 'http://127.0.0.1'
        self.client = TestClient(create_app(self.data, self.data), base_url=self.base, client=('127.0.0.1', 50000))
        sign_in(self.client.app, self.client)
        issued = self.client.post('/api/widget/tokens', json={'name': 'Pixel'}, headers={'Origin': self.base})
        self.assertEqual(issued.status_code, 200)
        self.token_id, self.token = issued.json()['id'], issued.json()['token']
        self.widget = TestClient(self.client.app, base_url=self.base)

    def usage(self, token):
        with patch('main.collect_usage', return_value=PROVIDERS):
            return self.widget.get('/api/widget/usage', headers={'Authorization': 'Bearer ' + token})

    def test_widget_token_reads_usage_after_engine_restart(self):
        self.widget = TestClient(create_app(self.data, self.data), base_url=self.base)
        result = self.usage(self.token)
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json()['providers'], PROVIDERS)
        device = self.client.get('/api/widget/tokens').json()['devices'][0]
        self.assertEqual(device['name'], 'Pixel')
        self.assertNotIn('hash', device)

    def test_widget_tap_skips_usage_cache(self):
        headers = {'Authorization': 'Bearer ' + self.token}
        with patch('main.collect_usage', return_value=PROVIDERS) as collect:
            self.assertEqual(self.widget.get('/api/widget/usage', headers=headers).status_code, 200)
            self.assertFalse(collect.call_args.kwargs['refresh'])
            self.assertEqual(self.widget.get('/api/widget/usage?refresh=1', headers=headers).status_code, 200)
            self.assertTrue(collect.call_args.kwargs['refresh'])

    def test_widget_token_cannot_reach_other_apis(self):
        headers = {'Authorization': 'Bearer ' + self.token}
        self.assertEqual(self.widget.get('/api/services', headers=headers).status_code, 401)
        self.assertEqual(self.widget.get('/api/usage', headers=headers).status_code, 401)
        self.assertEqual(self.widget.get('/api/widget/tokens', headers=headers).status_code, 401)
        self.assertEqual(self.usage('wrong-token').status_code, 401)

    def test_revoke_blocks_widget_immediately(self):
        result = self.client.delete(f'/api/widget/tokens/{self.token_id}', headers={'Origin': self.base})
        self.assertEqual(result.status_code, 200)
        self.assertEqual(self.client.get('/api/widget/tokens').json()['devices'], [])
        self.assertEqual(self.usage(self.token).status_code, 401)

    def test_native_app_header_replaces_origin_only_without_origin(self):
        app = TestClient(self.client.app, base_url=self.base)
        self.assertEqual(app.post('/api/logout', headers={'X-StackPad-Client': 'android'}).status_code, 200)
        self.assertEqual(app.post('/api/logout').status_code, 403)
        crafted = {'X-StackPad-Client': 'android', 'Origin': 'https://attacker.example'}
        self.assertEqual(app.post('/api/logout', headers=crafted).status_code, 403)

    def test_tokens_without_device_are_dropped(self):
        path = self.data / 'widget-tokens.json'
        records = json.loads(path.read_text('utf-8'))
        records.append({'id': 'old', 'name': 'Former app', 'hash': 'a' * 64, 'created_at': 0, 'last_used_at': None})
        path.write_text(json.dumps(records), 'utf-8')
        from widget_tokens import WidgetTokens
        tokens = WidgetTokens(lambda: self.data)
        self.assertEqual([r['id'] for r in tokens.records], [self.token_id])
        self.assertNotIn('Former app', path.read_text('utf-8'))

    def test_only_token_hash_is_stored(self):
        content = (self.data / 'widget-tokens.json').read_text('utf-8')
        self.assertNotIn(self.token, content)


if __name__ == '__main__':
    unittest.main()
