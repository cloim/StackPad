import runpy
import tempfile
import unittest
from pathlib import Path

import httpx
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
tools = runpy.run_path(str(ROOT / 'scripts' / 'dev-engine.py'))
create_app = tools['create_app']
installed_session = tools['installed_session']


class DevEngineTests(unittest.TestCase):
    def test_installed_session_enables_widgets_and_revocation_takes_effect(self):
        active = True

        def auth(request):
            self.assertEqual(request.url.path, '/api/auth')
            signed_in = active and request.headers.get('cookie') == 'stackpad_session=dev-fixture'
            return httpx.Response(200, json={'authenticated': signed_in, 'email': 'owner@example.test' if signed_in else None})

        origin = 'https://stackpad.example.test'
        with tempfile.TemporaryDirectory() as folder, httpx.Client(base_url='http://127.0.0.1:48731', transport=httpx.MockTransport(auth)) as installed:
            app = create_app(folder, ROOT / 'dist', session_lookup=lambda value: installed_session(installed, value))
            with TestClient(app, base_url=origin) as dev:
                self.assertEqual(dev.get('/api/system/metrics').status_code, 401)
                dev.cookies.set('stackpad_session', 'dev-fixture')
                self.assertEqual(dev.get('/api/system/metrics').status_code, 200)
                result = dev.put('/api/padsets/default/widget', json={'widget': 'system'}, headers={'Origin': origin})
                self.assertEqual(result.status_code, 200)
                self.assertEqual(dev.get('/api/services').json()['padsets'][0]['widget'], 'system')
                active = False
                self.assertEqual(dev.get('/api/system/metrics').status_code, 401)
