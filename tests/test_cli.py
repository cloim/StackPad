import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from main import create_app, VERSION


class CommandLineApiTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.work = Path(self.folder.name) / 'work'
        self.work.mkdir()
        self.app = create_app(self.folder.name, self.folder.name, control_token='cli-token')
        self.engine = self.app.state.engine
        self.client = TestClient(self.app, base_url='http://127.0.0.1:48731', client=('127.0.0.1', 50000))

    def call(self, *args, stdin='', lang='ko', token='cli-token'):
        response = self.client.post('/api/cli', json={'args': list(args), 'cwd': str(self.work), 'stdin': stdin},
                                    headers={'X-StackPad-Control': token, 'X-StackPad-Lang': lang})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def ok(self, *args, **options):
        result = self.call(*args, **options)
        self.assertEqual(result['exit_code'], 0, result['error'])
        return json.loads(result['output'])

    def test_requires_the_control_token_from_this_pc(self):
        self.assertEqual(self.client.post('/api/cli', json={'args': ['padset', 'list']}, headers={'X-StackPad-Control': 'wrong'}).status_code, 403)
        self.assertEqual(self.client.post('/api/cli', json={'args': ['padset', 'list']}, headers={'Origin': 'http://127.0.0.1:48731'}).status_code, 403)
        remote = TestClient(self.app, base_url='https://pc.example.ts.net', client=('127.0.0.1', 50001), headers={'X-Forwarded-For': '100.64.0.2'})
        self.assertEqual(remote.post('/api/cli', json={'args': ['padset', 'list']}, headers={'X-StackPad-Control': 'cli-token'}).status_code, 403)

    def test_help_version_and_usage_errors(self):
        result = self.call('help')
        self.assertEqual(result['exit_code'], 0)
        self.assertIn('padset list', result['output'])
        self.assertIn('StackPad command line', self.call('help', lang='en')['output'])
        self.assertIn('#22c55e', self.call('help', 'pad', lang='en')['output'])
        self.assertEqual(self.ok('version'), {'engine': VERSION})
        wrong = self.call('pad', 'fly')
        self.assertEqual(wrong['exit_code'], 2)
        self.assertIn('stackpad-cli help', wrong['error'])
        self.assertTrue(self.call('pad', 'fly', lang='en')['error'].startswith('Check the command:'))

    def test_padsets(self):
        added = self.ok('padset', 'add', '업무')
        lab = self.ok('padset', 'add', 'Lab')
        self.assertEqual(self.ok('padset', 'rename', 'lab', '실험')['id'], lab['id'])
        listing = self.ok('padset', 'order', '실험', added['id'])['padsets']
        self.assertEqual([s['id'] for s in listing], [lab['id'], added['id'], 'default'])
        self.assertEqual(listing[0]['free_slots'], list(range(16)))
        self.assertEqual(self.call('padset', 'add', ' 실험 ')['exit_code'], 1)
        missing = self.call('padset', 'delete', '없음', lang='en')
        self.assertEqual((missing['exit_code'], missing['error']), (1, 'Pad set not found: 없음'))
        self.ok('padset', 'delete', '업무')
        self.assertNotIn('업무', [s['name'] for s in self.engine.config['padsets']])

    def test_single_pad_lifecycle(self):
        self.ok('padset', 'add', '업무')
        added = self.ok('pad', 'add', '--name', 'API', '--command', 'uv run main.py', '--port', '8000', '--padset', '업무', '--color', '#3B82F6')['pad']
        self.assertEqual((added['slot'], added['padset'], added['type'], added['color']), (0, '업무', 'single', '#3b82f6'))
        self.assertEqual(added['components'][0]['cwd'], str(self.work.resolve()))
        second = self.ok('pad', 'add', '--name', 'Web', '--command', 'npm run dev', '--cwd', '.', '--padset', '업무')['pad']
        self.assertEqual(second['slot'], 1)
        shown = self.ok('pad', 'show', 'api')
        self.assertEqual(shown['input']['components'][0]['id'], added['id'])
        updated = self.ok('pad', 'update', 'API', '--port', 'none', '--name', 'Backend', '--autostart')['pad']
        self.assertEqual((updated['id'], updated['name'], updated['components'][0]['port'], updated['autostart']), (added['id'], 'Backend', None, True))
        self.assertEqual(updated['components'][0]['command'], 'uv run main.py')
        self.assertEqual(self.call('pad', 'move', 'Backend', '--slot', '1')['exit_code'], 1)
        moved = self.ok('pad', 'move', 'Backend', '--slot', '5', '--padset', 'default')['pad']
        self.assertEqual((moved['slot'], moved['padset_id']), (5, 'default'))
        self.assertEqual([p['name'] for p in self.ok('pad', 'list', '--padset', '업무')['pads']], ['Web'])
        self.ok('pad', 'delete', added['id'])
        self.assertEqual(len(self.ok('pad', 'list')['pads']), 1)

    def test_group_pad_from_json_on_standard_input(self):
        body = {'name': '앱', 'wait_ready': True, 'components': [
            {'kind': 'local', 'name': 'API', 'command': 'uv run api.py', 'cwd': str(self.work)},
            {'kind': 'local', 'name': 'Web', 'command': 'npm run dev', 'cwd': str(self.work), 'port': 5173}]}
        pad = self.ok('pad', 'add', '--json', '-', '--slot', '3', stdin=json.dumps(body))['pad']
        self.assertEqual((pad['type'], pad['slot'], pad['status'], [c['name'] for c in pad['components']]), ('group', 3, 'stopped', ['API', 'Web']))
        rejected = self.call('pad', 'update', '앱', '--command', 'x')
        self.assertEqual(rejected['exit_code'], 1)
        current = self.ok('pad', 'show', pad['id'])['input']
        current['components'][1]['port'] = 3000
        changed = self.ok('pad', 'update', '앱', '--json', '-', stdin=json.dumps(current))['pad']
        self.assertEqual(changed['components'][1]['port'], 3000)
        self.assertEqual([c['id'] for c in changed['components']], [c['id'] for c in pad['components']])
        bad = self.call('pad', 'add', '--json', '-', stdin='[1]')
        self.assertEqual(bad['exit_code'], 1)
        invalid = self.call('pad', 'add', '--name', 'X', '--command', 'a', '--cwd', 'missing-folder')
        self.assertEqual(invalid['exit_code'], 1)
        self.assertEqual(invalid['error'], 'cwd: 존재하는 폴더의 전체 경로를 입력해 주세요.')

    def test_run_control_routes_single_and_group_pads(self):
        single = self.ok('pad', 'add', '--name', 'API', '--command', 'uv run api.py')['pad']
        group = self.ok('pad', 'add', '--json', '-', stdin=json.dumps({'name': '묶음', 'components': [
            {'name': 'A', 'command': 'a', 'cwd': str(self.work)}, {'name': 'B', 'command': 'b', 'cwd': str(self.work)}]}))['pad']
        with patch.object(self.engine, 'start') as start, patch.object(self.engine, 'stop') as stop, patch.object(self.engine, 'restart') as restart, \
                patch.object(self.engine, 'group_action') as group_action:
            self.ok('pad', 'start', 'API', '--takeover')
            start.assert_called_once_with(single['id'], True)
            self.ok('pad', 'stop', 'api')
            stop.assert_called_once_with(single['id'])
            self.ok('pad', 'restart', single['id'])
            restart.assert_called_once_with(single['id'])
            self.ok('pad', 'start', '묶음')
            self.ok('pad', 'restart', '묶음')
            self.assertEqual([c.args[:2] for c in group_action.call_args_list], [(group['id'], 'start'), (group['id'], 'stop'), (group['id'], 'start')])
        with patch.object(self.engine, 'start', side_effect=ValueError('이미 실행 중인 서비스입니다.')):
            failed = self.call('pad', 'start', 'API', lang='en')
        self.assertEqual((failed['exit_code'], failed['error']), (1, 'The service is already running.'))
        with patch.object(self.engine, 'tail', side_effect=lambda sid: f'log {sid}'):
            self.assertEqual(self.call('pad', 'logs', 'API')['output'], f"log {single['id']}\n")
            both = self.call('pad', 'logs', '묶음')['output']
            self.assertIn('===== A =====', both)
            self.assertEqual(self.call('pad', 'logs', '묶음', '--component', 'b')['output'], f"log {group['components'][1]['id']}\n")

    def test_same_name_in_two_padsets_needs_an_id(self):
        self.ok('padset', 'add', '업무')
        self.ok('pad', 'add', '--name', 'API', '--command', 'a')
        self.ok('pad', 'add', '--name', 'API', '--command', 'a', '--padset', '업무')
        ambiguous = self.call('pad', 'show', 'API')
        self.assertEqual(ambiguous['exit_code'], 1)
        self.assertIn('ID', ambiguous['error'])


if __name__ == '__main__':
    unittest.main()
