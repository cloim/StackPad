import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from main import create_app
from auth_helper import sign_in
from google_auth import CALLBACK_PATH, GoogleAuth
from session_store import SESSION_TTL

CLIENT_ID = 'stackpad-test.apps.googleusercontent.com'
EXTERNAL = 'https://pc.tail1234.ts.net:48731'
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def id_token(nonce, **changes):
    claims = {'iss': 'https://accounts.google.com', 'aud': CLIENT_ID, 'sub': '1', 'email': 'owner@example.com', 'email_verified': True,
              'nonce': nonce, 'iat': int(time.time()), 'exp': int(time.time()) + 600, **changes}
    return jwt.encode(claims, KEY, algorithm='RS256')


class FakeKeys:
    def get_signing_key_from_jwt(self, token):
        return SimpleNamespace(key=KEY.public_key())


class FakeTokenEndpoint:
    """Answers the code exchange with an ID token for the email chosen by the test."""
    def __init__(self, google):
        self.google = google
        self.email = 'owner@example.com'
        self.calls = []

    def post(self, url, data):
        self.calls.append(data)
        flow_nonce = self.nonce
        return SimpleNamespace(status_code=200, json=lambda: {'id_token': id_token(flow_nonce, email=self.email)})


class GoogleAuthTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.data = Path(self.folder.name)
        self.app = create_app(self.data, self.data)
        self.google = self.app.state.google
        self.google._keys = FakeKeys()
        self.token = FakeTokenEndpoint(self.google)
        self.google.http = self.token
        self.local = self.client('http://127.0.0.1:48731', '127.0.0.1')

    def client(self, base, host, forwarded=False):
        client = TestClient(self.app, base_url=base, client=(host, 50000), follow_redirects=False)
        client.headers['Origin'] = base
        if forwarded:
            client.headers['X-Forwarded-For'] = '100.64.0.2'
        return client

    def external(self):
        return self.client(EXTERNAL, '127.0.0.1', forwarded=True)

    def configure(self):
        self.assertEqual(self.local.put('/api/auth/client', json={'client_id': CLIENT_ID, 'client_secret': 'secret'}).status_code, 200)

    def sign_in_with_google(self, client, email='owner@example.com', ticket=None):
        start = client.get('/api/auth/google/start' + (f'?ticket={ticket}' if ticket else ''))
        self.assertEqual(start.status_code, 303, start.text)
        query = parse_qs(urlsplit(start.headers['location']).query)
        state = query['state'][0]
        self.token.nonce = self.google.flows[state]['nonce']
        self.token.email = email
        return client.get(CALLBACK_PATH, params={'state': state, 'code': 'code'}), query

    def test_first_local_sign_in_becomes_owner(self):
        self.assertFalse(self.local.get('/api/auth').json()['configured'])
        self.configure()
        response, query = self.sign_in_with_google(self.local)
        self.assertEqual(query['client_id'], [CLIENT_ID])
        self.assertEqual(query['redirect_uri'], ['http://127.0.0.1:48731' + CALLBACK_PATH])
        self.assertEqual(query['code_challenge_method'], ['S256'])
        self.assertEqual(self.token.calls[0]['redirect_uri'], 'http://127.0.0.1:48731' + CALLBACK_PATH)
        self.assertTrue(self.token.calls[0]['code_verifier'])
        self.assertEqual((response.status_code, response.headers['location']), (303, '/'))
        cookie = response.headers.get_list('set-cookie')
        self.assertTrue(any(f'Max-Age={SESSION_TTL}' in c and 'HttpOnly' in c and 'SameSite=lax' in c for c in cookie))
        state = self.local.get('/api/auth').json()
        self.assertEqual((state['authenticated'], state['email'], state['owner']), (True, 'owner@example.com', True))
        self.assertEqual(self.google.accounts(), ['owner@example.com'])

    def test_external_needs_owner_and_allowed_account(self):
        self.configure()
        self.google.save_external_url(EXTERNAL)
        external = self.external()
        response, query = self.sign_in_with_google(external)
        self.assertEqual(query['redirect_uri'], [EXTERNAL + CALLBACK_PATH])
        self.assertIn('auth_error', response.headers['location'])
        self.assertIsNone(self.google.owner)
        self.sign_in_with_google(self.local)
        response, _ = self.sign_in_with_google(external, 'stranger@example.com')
        self.assertIn('auth_error', response.headers['location'])
        self.assertFalse(external.get('/api/auth').json()['authenticated'])
        response, _ = self.sign_in_with_google(external)
        self.assertEqual(response.headers['location'], '/')
        self.assertTrue(any('Secure' in c for c in response.headers.get_list('set-cookie')))
        self.assertTrue(external.get('/api/auth').json()['authenticated'])
        self.assertFalse(external.get('/api/auth').json()['local'])

    def test_unknown_external_host_cannot_start(self):
        self.configure()
        self.google.save_external_url(EXTERNAL)
        other = self.client('https://other.example.com', '127.0.0.1', forwarded=True)
        self.assertEqual(other.get('/api/auth/google/start').status_code, 403)

    def test_external_host_without_forwarding_is_not_local(self):
        self.google.save_external_url(EXTERNAL)
        spoof = self.client(EXTERNAL, '127.0.0.1')
        self.assertFalse(spoof.get('/api/auth').json()['local'])
        self.assertEqual(spoof.put('/api/auth/client', json={'client_id': CLIENT_ID, 'client_secret': 'x'}).status_code, 403)

    def test_callback_rejects_other_browser_state(self):
        self.configure()
        start = self.local.get('/api/auth/google/start')
        state = parse_qs(urlsplit(start.headers['location']).query)['state'][0]
        other = self.client('http://127.0.0.1:48731', '127.0.0.1')
        response = other.get(CALLBACK_PATH, params={'state': state, 'code': 'code'})
        self.assertIn('auth_error', response.headers['location'])
        self.assertEqual(self.token.calls, [])

    def test_setup_requires_session_after_owner(self):
        self.configure()
        self.sign_in_with_google(self.local)
        anonymous = self.client('http://127.0.0.1:48731', '127.0.0.1')
        self.assertEqual(anonymous.get('/api/auth/settings').status_code, 401)
        settings = self.local.get('/api/auth/settings').json()
        self.assertEqual(settings['redirect_uris'], ['http://127.0.0.1:48731' + CALLBACK_PATH])
        self.assertNotIn('client_secret', settings)
        self.assertEqual(self.external().get('/api/auth/settings').status_code, 403)

    def test_desktop_ticket_signs_in_the_app_window(self):
        self.configure()
        with patch('main.os.startfile', create=True) as opened:
            ticket = self.local.post('/api/auth/desktop').json()
        self.assertIn(f"ticket={ticket['ticket']}", opened.call_args[0][0])
        self.assertTrue(self.local.post('/api/auth/desktop/claim', json=ticket).json()['pending'])
        browser = self.client('http://127.0.0.1:48731', '127.0.0.1')
        response, _ = self.sign_in_with_google(browser, ticket=ticket['ticket'])
        self.assertEqual(response.status_code, 200)
        self.assertFalse(browser.get('/api/auth').json()['authenticated'])
        claimed = self.local.post('/api/auth/desktop/claim', json=ticket)
        self.assertFalse(claimed.json()['pending'])
        self.assertTrue(self.local.get('/api/auth').json()['authenticated'])
        self.assertEqual(self.local.post('/api/auth/desktop/claim', json=ticket).status_code, 409)

    def test_accounts_and_revocation(self):
        sign_in(self.app, self.local)
        self.assertEqual(self.local.post('/api/auth/accounts', json={'email': 'Friend@Example.com'}).json()['email'], 'friend@example.com')
        friend = self.external()
        self.google.save_external_url(EXTERNAL)
        sign_in(self.app, friend, 'friend@example.com')
        self.assertEqual(friend.get('/api/services').status_code, 200)
        self.assertEqual(friend.post('/api/auth/accounts', json={'email': 'x@example.com'}).status_code, 403)
        self.assertEqual(self.local.delete('/api/auth/accounts/owner@example.com').status_code, 409)
        self.assertEqual(self.local.delete('/api/auth/accounts/friend@example.com').status_code, 200)
        self.assertEqual(friend.get('/api/services').status_code, 401)

    def test_pairing_creates_revocable_device(self):
        sign_in(self.app, self.local)
        self.assertEqual(self.local.post('/api/pairing').status_code, 409)
        self.google.save_external_url(EXTERNAL)
        pairing = self.local.post('/api/pairing').json()
        self.assertTrue(pairing['link'].startswith('stackpad://pair?'))
        phone = TestClient(self.app, base_url=EXTERNAL, client=('127.0.0.1', 50001), headers={'X-StackPad-Client': 'android', 'X-Forwarded-For': '100.64.0.3'})
        self.assertEqual(phone.post('/api/pairing/claim', json={'code': 'wrong', 'name': 'Pixel'}).status_code, 403)
        claimed = phone.post('/api/pairing/claim', json={'code': pairing['code'], 'name': 'Pixel'})
        self.assertEqual(claimed.status_code, 200, claimed.text)
        self.assertEqual(phone.post('/api/pairing/claim', json={'code': pairing['code'], 'name': 'Pixel'}).status_code, 403)
        self.assertEqual(phone.get('/api/services').status_code, 200)
        widget = phone.post('/api/widget/tokens', json={'name': 'Pixel'}).json()
        devices = self.local.get('/api/devices').json()['devices']
        self.assertEqual([d['name'] for d in devices], ['Pixel'])
        self.assertEqual(phone.get('/api/devices').json()['current'], devices[0]['id'])
        self.assertEqual(self.local.delete(f"/api/devices/{devices[0]['id']}").status_code, 200)
        self.assertEqual(phone.get('/api/services').status_code, 401)
        with patch('main.collect_usage', return_value=[]):
            self.assertEqual(phone.get('/api/widget/usage', headers={'Authorization': 'Bearer ' + widget['token']}).status_code, 401)

    def test_pairing_code_expires(self):
        sign_in(self.app, self.local)
        self.google.save_external_url(EXTERNAL)
        code = self.local.post('/api/pairing').json()['code']
        with patch('google_auth.time.time', return_value=time.time() + 301):
            with self.assertRaises(PermissionError):
                self.google.claim_pairing(code)


class TokenVerificationTests(unittest.TestCase):
    def setUp(self):
        engine = SimpleNamespace(config={'auth': {'client_id': CLIENT_ID, 'client_secret': 'secret'}}, lock=None)
        self.google = GoogleAuth(engine, http=object())
        self.google._keys = FakeKeys()

    def test_accepts_verified_google_token(self):
        self.assertEqual(self.google.verify(id_token('n', email='Owner@Example.com'), 'n'), 'owner@example.com')

    def test_rejects_tampered_claims(self):
        for changes in ({'aud': 'other.apps.googleusercontent.com'}, {'iss': 'https://evil.example'}, {'email_verified': False},
                        {'exp': int(time.time()) - 10}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.google.verify(id_token('n', **changes), 'n')
        with self.assertRaises(ValueError):
            self.google.verify(id_token('n'), 'other-nonce')
        other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        forged = jwt.encode({'iss': 'https://accounts.google.com', 'aud': CLIENT_ID, 'sub': '1', 'email': 'owner@example.com',
                             'email_verified': True, 'nonce': 'n', 'iat': int(time.time()), 'exp': int(time.time()) + 600}, other_key, algorithm='RS256')
        with self.assertRaises(ValueError):
            self.google.verify(forged, 'n')


if __name__ == '__main__':
    unittest.main()
