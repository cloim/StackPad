import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
import groups
from engine import Engine
from groups import PadInput, automatic_local_url
from main import create_app
from auth_helper import sign_in


class PadLinkTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.engine = Engine(Path(self.folder.name) / 'data')

    def component(self, name='App', port=None, health_url=''):
        return {'name': name, 'command': 'echo', 'cwd': self.folder.name, 'port': port, 'health_url': health_url}

    def pad(self, components, **links):
        return PadInput(name='Pad', slot=0, color='#3b82f6', components=components, **links)

    def test_automatic_local_url(self):
        self.assertEqual(automatic_local_url([{'port': 48085, 'health_url': 'http://127.0.0.1:48085/webapps/'}]), 'http://127.0.0.1:48085/webapps/')
        self.assertEqual(automatic_local_url([{'port': 8000, 'health_url': 'http://localhost:8000/health'}]), 'http://localhost:8000/')
        self.assertEqual(automatic_local_url([{'port': 3000, 'health_url': 'http://127.0.0.1:9999/'}]), 'http://localhost:3000/')
        group = [{'port': 41433, 'health_url': 'http://127.0.0.1:41433/api/v1/auth/session'}, {'port': 41434, 'health_url': 'http://127.0.0.1:41434/'}]
        self.assertEqual(automatic_local_url(group), 'http://127.0.0.1:41434/')
        self.assertEqual(automatic_local_url([{'port': 5173, 'health_url': ''}, {'port': None}]), 'http://localhost:5173/')
        self.assertEqual(automatic_local_url([{'kind': 'remote', 'remote': {}}, {'port': None}]), '')

    def test_url_validation(self):
        with self.assertRaises(ValidationError):
            self.pad([self.component()], domain_url='javascript:alert(1)')
        with self.assertRaises(ValidationError):
            self.pad([self.component()], domain_url='https://user:pw@app.example.com/')
        with self.assertRaises(ValidationError):
            self.pad([self.component()], local_url='http://192.168.0.5:8000/')
        values = self.pad([self.component()], domain_url=' https://app.example.com/ ', local_url='http://127.0.0.1:8000/app/')
        self.assertEqual(values.domain_url, 'https://app.example.com/')

    def test_links_follow_single_and_group_pads(self):
        pad_id = self.engine.save_pad(self.pad([self.component(port=8000)], domain_url='https://one.example.com/'))
        self.assertEqual(self.engine.pad_links()[pad_id], {'domain': 'https://one.example.com/', 'local': 'http://localhost:8000/'})
        components = [{**self.component('Backend', 8001), 'id': pad_id}, self.component('Frontend', 5173)]
        group_id = self.engine.save_pad(self.pad(components, domain_url='https://two.example.com/', local_url='http://localhost:5173/login/'), pad_id)
        links = self.engine.pad_links()
        self.assertEqual(links[group_id], {'domain': 'https://two.example.com/', 'local': 'http://localhost:5173/login/'})
        self.assertNotIn(pad_id, links)
        self.assertNotIn('domain_url', self.engine.service(pad_id))
        members = self.engine.group(group_id)['member_ids']
        self.engine.save_group(groups.GroupInput(name='Pad', member_ids=members, slot=0, color='#3b82f6'), group_id)
        self.assertEqual(self.engine.pad_links()[group_id]['domain'], 'https://two.example.com/')
        single = self.engine.save_pad(self.pad([{**self.component('Backend', 8001), 'id': members[0]}]), group_id)
        self.assertEqual(self.engine.pad_links()[single], {'domain': '', 'local': 'http://localhost:8001/'})

    def test_open_link_is_local_only(self):
        app = create_app(Path(self.folder.name) / 'api', self.folder.name)
        local = TestClient(app, base_url='http://127.0.0.1', client=('127.0.0.1', 50000), headers={'Origin': 'http://127.0.0.1'})
        sign_in(app, local)
        external = TestClient(app, base_url='https://deck.example.com', client=('127.0.0.1', 50000), headers={'Origin': 'https://deck.example.com', 'X-Forwarded-For': '203.0.113.9'})
        sign_in(app, external)
        body = {'name': 'Pad', 'slot': 0, 'color': '#3b82f6', 'domain_url': 'https://one.example.com/', 'components': [self.component(port=8000)]}
        pad_id = local.post('/api/pads', json=body).json()['id']
        self.assertEqual(external.get('/api/services').json()['links'][pad_id]['domain'], 'https://one.example.com/')
        with patch.object(groups.os, 'startfile', create=True) as startfile:
            self.assertEqual(external.post(f'/api/pads/{pad_id}/open', json={'target': 'local'}).status_code, 403)
            response = local.post(f'/api/pads/{pad_id}/open', json={'target': 'local'})
            self.assertEqual(response.json()['url'], 'http://localhost:8000/')
            startfile.assert_called_once_with('http://localhost:8000/')
            self.assertEqual(local.post(f'/api/pads/{pad_id}/open', json={'target': 'other'}).status_code, 422)
            self.assertEqual(local.post('/api/pads/missing/open', json={'target': 'domain'}).status_code, 404)
        body.update(domain_url='', components=[{**self.component(port=8000), 'id': pad_id}])
        local.put(f'/api/pads/{pad_id}', json=body)
        self.assertEqual(local.post(f'/api/pads/{pad_id}/open', json={'target': 'domain'}).status_code, 409)


if __name__ == '__main__':
    unittest.main()
