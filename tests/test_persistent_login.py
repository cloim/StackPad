import hashlib
import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from main import create_app
from auth_helper import sign_in
from session_store import SESSION_TTL, SessionStore


class PersistentLoginTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.data = Path(self.folder.name)
        self.addCleanup(self.folder.cleanup)
        self.base = 'http://127.0.0.1'
        self.client = TestClient(create_app(self.data, self.data), base_url=self.base, client=('127.0.0.1', 50000))
        sign_in(self.client.app, self.client)
        self.cookies = dict(self.client.cookies)

    def test_refresh_and_engine_restart_keep_login(self):
        for app in (self.client.app, create_app(self.data, self.data)):
            client = TestClient(app, base_url=self.base, cookies=self.cookies)
            self.assertTrue(client.get('/api/auth').json()['authenticated'])
            self.assertEqual(client.get('/api/auth').json()['email'], 'owner@example.com')
            self.assertEqual(client.get('/api/services').status_code, 200)

    def test_logout_revokes_saved_login(self):
        result = self.client.post('/api/logout', headers={'Origin': self.base})
        self.assertEqual(result.status_code, 200)
        replay = TestClient(create_app(self.data, self.data), base_url=self.base, cookies=self.cookies)
        self.assertFalse(replay.get('/api/auth').json()['authenticated'])
        self.assertEqual(replay.get('/api/services').status_code, 401)

    def test_expiry_revokes_saved_login(self):
        with patch('time.time', return_value=time.time() + SESSION_TTL + 1):
            self.assertFalse(self.client.get('/api/auth').json()['authenticated'])
            self.assertEqual(self.client.get('/api/services').status_code, 401)
            restarted = TestClient(create_app(self.data, self.data), base_url=self.base, cookies=self.cookies)
            self.assertEqual(restarted.get('/api/services').status_code, 401)

    def test_saved_hash_cannot_be_used_as_browser_credential(self):
        content = (self.data / 'sessions.json').read_text('utf-8')
        records = json.loads(content)
        for name, value in self.cookies.items():
            self.assertNotIn(value, content)
            digest = hashlib.sha256(value.encode()).hexdigest()
            self.assertIn(digest, records)
            forged = TestClient(create_app(self.data, self.data), base_url=self.base, cookies={name: digest})
            self.assertEqual(forged.get('/api/services').status_code, 401)

    def test_origin_guard(self):
        self.assertEqual(self.client.post('/api/logout', headers={'Origin': 'https://other.test'}).status_code, 403)

    def test_invalid_store_fails_closed(self):
        (self.data / 'sessions.json').write_text('invalid', 'utf-8')
        store = SessionStore(self.data)
        self.assertEqual(len(store), 0)
        self.assertIsNone(store.get(None))

    def test_former_password_sessions_are_dropped(self):
        (self.data / 'sessions.json').write_text(json.dumps({'a' * 64: time.time() + 3600}), 'utf-8')
        self.assertEqual(len(SessionStore(self.data)), 0)


if __name__ == '__main__':
    unittest.main()
