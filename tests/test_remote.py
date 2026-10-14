import json
import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
import remote
from engine import Engine, RemoteServiceInput, ServiceInput
from groups import PadInput
from main import create_app
from auth_helper import sign_in

FAKE = [getattr(sys, '_base_executable', sys.executable), str(Path(__file__).with_name('fake_ssh.py'))]


def spec(host='app', **values):
    return {'host': host, 'start': 'start-app', 'stop': 'stop-app', 'status': 'status-app', 'logs': 'logs-app', **values}


class RemoteTestCase(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory(prefix='stackpad-remote-')
        self.addCleanup(self.folder.cleanup)
        self.state = Path(self.folder.name) / 'ssh'
        self.state.mkdir()
        self.ssh_config = Path(self.folder.name) / 'ssh_config'
        self.ssh_config.write_text('Host *\n  ServerAliveInterval 30\nHost app web\n  HostName 10.0.0.5\nHost=nas\n  HostName nas.example.com\nMatch host x\n  HostName ignored\n', 'utf-8')
        patches = [patch.dict(os.environ, {'FAKE_SSH_STATE': str(self.state), 'STACKPAD_SSH_CONFIG': str(self.ssh_config)}), patch.object(remote, 'ssh_executable', lambda: FAKE)]
        for item in patches:
            item.start()
            self.addCleanup(item.stop)
        self.engine = Engine(Path(self.folder.name) / 'data')

    def pad(self, components, name='Remote', slot=0, autostart=False):
        return PadInput(name=name, slot=slot, color='#3b82f6', autostart=autostart, wait_ready=False, components=components)

    def add_remote(self, slot=0, **values):
        return self.engine.save_pad(self.pad([{'kind': 'remote', 'name': 'API', 'remote': spec(**values)}], slot=slot))

    def snapshot(self, service_id):
        return next(s for s in self.engine.snapshot() if s['id'] == service_id)

    def calls(self):
        path = self.state / 'calls.log'
        return path.read_text('utf-8').splitlines() if path.exists() else []


class RemoteInputTests(RemoteTestCase):
    def test_host_must_not_look_like_an_option(self):
        for host in ('-oProxyCommand=calc', 'app;rm', 'a b', 'user@-x'):
            with self.assertRaises(ValidationError, msg=host):
                remote.RemoteSpec(**spec(host))
        for host in ('app', 'deploy@10.0.0.5', 'deploy@server.local:2222'):
            self.assertEqual(remote.RemoteSpec(**spec(host)).host, host)

    def test_commands_are_single_lines_and_required(self):
        with self.assertRaises(ValidationError):
            remote.RemoteSpec(**spec(start='start\nrm -rf /'))
        with self.assertRaises(ValidationError):
            remote.RemoteSpec(**spec(status='  '))

    def test_health_url_limited_to_private_or_registered_host(self):
        self.assertTrue(remote.RemoteSpec(**spec(health_url='http://10.0.0.5:8000/health')).health_url)
        self.assertTrue(remote.RemoteSpec(**spec('nas', health_url='https://nas.example.com/ping')).health_url)
        self.assertTrue(remote.RemoteSpec(**spec('ops@app:2200', health_url='http://app:8000/')).health_url)
        for url in ('http://example.com/', 'http://user:pw@10.0.0.5/', 'file:///etc/passwd', 'http://8.8.8.8/'):
            with self.assertRaises(ValidationError, msg=url):
                remote.RemoteSpec(**spec(health_url=url))

    def test_ssh_config_aliases_skip_wildcards_and_match_blocks(self):
        hosts = remote.ssh_hosts()
        self.assertEqual([h['alias'] for h in hosts], ['app', 'web', 'nas'])
        self.assertEqual(hosts[1]['hostname'], '10.0.0.5')
        self.assertEqual(hosts[2]['hostname'], 'nas.example.com')

    def test_remote_service_never_autostarts(self):
        with self.assertRaises(ValidationError):
            RemoteServiceInput(name='API', remote=spec(), slot=0, autostart=True)
        pad_id = self.engine.save_pad(self.pad([{'kind': 'remote', 'name': 'API', 'remote': spec()}], autostart=True))
        self.assertFalse(self.engine.service(pad_id)['autostart'])

    def test_switching_kind_drops_previous_settings(self):
        local_id = self.engine.save_pad(self.pad([{'name': 'API', 'command': 'echo hi', 'cwd': self.folder.name, 'port': 8123}]))
        self.engine.save_pad(self.pad([{'id': local_id, 'kind': 'remote', 'name': 'API', 'remote': spec()}]), local_id)
        service = self.engine.service(local_id)
        self.assertEqual(service['kind'], 'remote')
        self.assertFalse({'command', 'cwd', 'port', 'health_url'} & set(service))
        self.engine.add(ServiceInput(name='API', command='echo hi', cwd=self.folder.name, slot=0), local_id)
        service = self.engine.service(local_id)
        self.assertEqual(service['kind'], 'local')
        self.assertNotIn('remote', service)

    def test_legacy_services_without_kind_stay_local(self):
        data = Path(self.folder.name) / 'legacy'
        data.mkdir()
        (data / 'config.json').write_text(json.dumps({'services': [{'id': 'old', 'name': 'Old', 'command': 'echo', 'cwd': self.folder.name, 'port': None, 'health_url': '', 'color': '#22c55e', 'autostart': False, 'slot': 0, 'runtime': None, 'error': ''}]}), 'utf-8')
        item = Engine(data).snapshot()[0]
        self.assertEqual(item['status'], 'stopped')
        self.assertFalse(item['active'])


class SshRunnerTests(RemoteTestCase):
    def test_batch_options_and_port_are_passed(self):
        with patch.object(remote.subprocess, 'run', wraps=remote.subprocess.run) as run:
            result = remote.run_ssh('ops@app:2222', 'true', 5)
        self.assertEqual(result['code'], 0)
        args = run.call_args.args[0]
        self.assertIn('BatchMode=yes', args)
        self.assertIn('StrictHostKeyChecking=yes', args)
        self.assertEqual(args[-3:], ['2222', 'ops@app', 'true'])
        self.assertEqual(run.call_args.kwargs['stdin'], remote.subprocess.DEVNULL)

    def test_timeout_and_connection_failures(self):
        result = remote.run_ssh('slow', 'true', 1)
        self.assertIsNone(result['code'])
        self.assertTrue(remote.connection_failed(result))
        result = remote.run_ssh('down', 'true', 5)
        self.assertEqual(result['code'], 255)
        self.assertIn('Connection refused', remote.summarize(result, 'down'))
        result = remote.run_ssh('newhost', 'true', 5)
        self.assertIn('ssh newhost', remote.summarize(result, 'newhost'))

    def test_same_host_runs_at_most_two_connections(self):
        active, peak, guard = [0], [0], threading.Lock()

        def slow_run(host, command, timeout):
            with guard:
                active[0] += 1
                peak[0] = max(peak[0], active[0])
            time.sleep(0.2)
            with guard:
                active[0] -= 1
            return {'code': 0, 'output': '', 'error': ''}
        with patch.object(remote, 'run_ssh', slow_run):
            threads = [threading.Thread(target=self.engine.ssh, args=('app', 'true', 'test')) for _ in range(5)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
        self.assertEqual(peak[0], 2)


class RemoteLifecycleTests(RemoteTestCase):
    def test_start_status_logs_and_stop(self):
        service_id = self.add_remote()
        self.assertEqual(self.snapshot(service_id)['status'], 'checking')
        self.engine.probe(service_id)
        self.assertEqual(self.snapshot(service_id)['status'], 'stopped')
        self.engine.start(service_id)
        item = self.snapshot(service_id)
        self.assertEqual(item['status'], 'starting')
        self.assertTrue(item['active'])
        self.assertEqual(item['last']['action'], 'start')
        self.assertIn('started', item['last']['output'])
        self.engine.probe(service_id)
        item = self.snapshot(service_id)
        self.assertEqual(item['status'], 'running')
        self.assertIsNotNone(item['checked_ago'])
        self.assertIsNone(item['pid'])
        with self.assertRaises(ValueError):
            self.engine.start(service_id)
        self.assertIn('line 2 한글', self.engine.tail(service_id))
        self.engine.restart(service_id)
        self.assertEqual(self.snapshot(service_id)['status'], 'starting')
        self.engine.stop(service_id)
        self.assertEqual(self.snapshot(service_id)['status'], 'stopped')
        self.engine.probe(service_id)
        self.assertFalse(self.snapshot(service_id)['active'])
        before = len(self.calls())
        self.engine.stop(service_id)
        self.assertEqual(len(self.calls()), before, 'Stopping a stopped remote service must not run ssh')

    def test_check_overlapping_a_stop_is_discarded(self):
        service_id = self.add_remote()
        self.engine.start(service_id)
        self.engine.probe(service_id)
        original = self.engine.ssh

        def racing(host, command, action):
            result = original(host, command, action)
            self.engine.ssh = original
            self.engine.stop(service_id)
            return result
        self.engine.ssh = racing
        self.engine.probe(service_id)
        self.assertEqual(self.snapshot(service_id)['status'], 'stopped')

    def test_start_that_never_reports_running_becomes_unhealthy(self):
        service_id = self.add_remote(start='start-later')
        self.engine.start(service_id)
        self.engine.probe(service_id)
        self.assertEqual(self.snapshot(service_id)['status'], 'starting')
        self.engine.remote_states[service_id]['pending'] -= 30
        self.engine.probe(service_id)
        item = self.snapshot(service_id)
        self.assertEqual(item['status'], 'unhealthy')
        self.assertTrue(item['active'])
        self.assertIn('상태 명령', item['message'])

    def test_unreachable_host(self):
        service_id = self.add_remote(host='down')
        self.engine.probe(service_id)
        item = self.snapshot(service_id)
        self.assertEqual(item['status'], 'unreachable')
        self.assertFalse(item['active'])
        self.assertIn('Connection refused', item['message'])
        with self.assertRaises(ValueError) as caught:
            self.engine.start(service_id)
        self.assertIn('Connection refused', str(caught.exception))
        self.assertIn('[로그 명령 실패]', self.engine.tail(service_id))

    def test_failed_command_explains_sudo(self):
        service_id = self.add_remote(start='sudo-fail')
        with self.assertRaises(ValueError) as caught:
            self.engine.start(service_id)
        self.assertIn('sudoers', str(caught.exception))
        self.engine.probe(service_id)
        item = self.snapshot(service_id)
        self.assertEqual(item['status'], 'stopped')
        self.assertIn('sudoers', item['message'])

    def test_logs_are_cached_and_optional(self):
        service_id = self.add_remote()
        self.engine.tail(service_id)
        self.engine.tail(service_id)
        self.assertEqual(sum('logs-app' in line for line in self.calls()), 1)
        other = self.add_remote(slot=1, logs='')
        self.assertIn('로그 명령이 등록되지 않았습니다', self.engine.tail(other))

    def test_remote_pad_cannot_open_in_code_and_can_be_deleted_while_running(self):
        service_id = self.add_remote()
        self.engine.start(service_id)
        with self.assertRaises(ValueError):
            self.engine.pad_folder(service_id)
        self.engine.delete_pad(service_id)
        self.assertFalse(self.engine.config['services'])
        self.assertNotIn(service_id, self.engine.remote_states)

    def test_mixed_group_starts_in_order_and_skips_remote_at_boot(self):
        components = [{'kind': 'remote', 'name': 'DB', 'remote': spec('db')}, {'name': 'Sleep', 'command': f'"{sys.executable}" -c "import time; time.sleep(60)"', 'cwd': self.folder.name}]
        group_id = self.engine.save_pad(self.pad(components, autostart=True))
        remote_id, local_id = self.engine.group(group_id)['member_ids']
        self.addCleanup(lambda: self.engine.owned(self.engine.service(local_id)) and self.engine.stop(local_id))
        self.engine.group_action(group_id, 'start', skip_remote=True)
        self.assertNotIn('db\tstart-app', self.calls())
        self.engine.stop(local_id)
        self.engine.probe(remote_id)
        self.engine.group_action(group_id, 'start')
        self.assertIn('db\tstart-app', self.calls())
        self.assertTrue(self.engine.active(remote_id))
        self.engine.group_action(group_id, 'stop')
        self.assertIn('db\tstop-app', self.calls())
        self.assertFalse(self.engine.active(remote_id))
        self.assertFalse(self.engine.active(local_id))


class RemoteApiTests(RemoteTestCase):
    def client(self, base, host):
        if not hasattr(self, 'app'):
            self.app = create_app(Path(self.folder.name) / 'api', self.folder.name)
        client = TestClient(self.app, base_url=base, client=(host, 50000))
        client.headers['Origin'] = base
        return client

    def test_remote_registration_is_local_only(self):
        local = self.client('http://127.0.0.1', '127.0.0.1')
        sign_in(self.app, local)
        body = {'name': 'API', 'slot': 0, 'color': '#3b82f6', 'autostart': False, 'wait_ready': False, 'components': [{'kind': 'remote', 'name': 'API', 'remote': spec()}]}
        external = self.client('https://deck.example.com', '127.0.0.1')
        external.headers['X-Forwarded-For'] = '203.0.113.9'
        sign_in(self.app, external)
        self.assertEqual(external.post('/api/pads', json=body).status_code, 403)
        response = local.post('/api/pads', json=body)
        self.assertEqual(response.status_code, 200, response.text)
        pad_id = response.json()['id']
        local_body = {**body, 'components': [{'id': pad_id, 'name': 'API', 'command': 'echo', 'cwd': self.folder.name}]}
        self.assertEqual(external.put(f'/api/pads/{pad_id}', json=local_body).status_code, 403)
        self.assertEqual(external.put(f'/api/services/{pad_id}', json={'kind': 'remote', 'name': 'API', 'slot': 0, 'color': '#3b82f6', 'remote': spec()}).status_code, 403)
        self.assertEqual(external.post('/api/remote/test', json={'host': 'app'}).status_code, 403)
        self.assertEqual(local.put(f'/api/services/{pad_id}', json={'kind': 'remote', 'name': 'API 2', 'slot': 0, 'color': '#3b82f6', 'remote': spec()}).status_code, 200)
        self.assertEqual(external.post(f'/api/services/{pad_id}/start').status_code, 200)
        self.assertEqual(external.get(f'/api/services/{pad_id}/logs').status_code, 200)
        item = next(s for s in external.get('/api/services').json()['services'] if s['id'] == pad_id)
        self.assertEqual((item['kind'], item['status'], item['name']), ('remote', 'starting', 'API 2'))
        self.assertEqual(local.get('/api/remote/hosts').json()['hosts'], ['app', 'web', 'nas'])
        self.assertEqual(local.post('/api/remote/test', json={'host': 'app'}).json()['ok'], True)
        result = local.post('/api/remote/test', json={'host': 'down'}).json()
        self.assertFalse(result['ok'])
        self.assertEqual(local.post('/api/remote/test', json={'host': '-oProxyCommand=calc'}).status_code, 409)


if __name__ == '__main__':
    unittest.main()
