import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from cli import all_pads, pad_status
from engine import Engine
from groups import PadInput


class PadDesiredStateTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.engine = Engine(self.directory.name)
        self.daemon_up = True
        self.running = {}
        self.mock = patch('docker_services.docker_cli', side_effect=self.cli)
        self.mock.start()
        self.addCleanup(self.mock.stop)

    def cli(self, *args):
        if not self.daemon_up:
            raise ValueError('Docker 데몬 연결과 컨테이너 상태를 확인해 주세요.')
        if args[0] == 'inspect':
            target = args[-1]
            if args[2] == '{{.Id}}':
                cid = (target.encode().hex() * 16)[:64]
                self.running.setdefault(cid, False)
                return cid + '\n'
            return json.dumps({
                'state': {'Running': self.running.get(target, False), 'ExitCode': 0, 'StartedAt': '2026-10-12T00:00:00Z'},
                'name': '/svc',
                'ports': {'5432/tcp': None},
            })
        if args[0] == 'start':
            self.running[args[-1]] = True
        elif args[0] == 'stop':
            self.running[args[-1]] = False
        return ''

    def pad_view(self, pad_id):
        return next(p for p in all_pads(self.engine) if p['id'] == pad_id)

    def refresh_docker_samples(self):
        for service in self.engine.config['services']:
            if service.get('kind') == 'docker':
                self.engine.samples[service['id']] = self.engine.docker_state(service)

    def test_stopped_group_with_unreachable_docker_stays_stopped_while_components_keep_diagnostics(self):
        gid = self.engine.save_pad(PadInput(
            name='Halla Dev',
            slot=0,
            components=[
                {'name': 'PostgreSQL', 'kind': 'docker', 'container': 'pg'},
                {'name': 'Redis', 'kind': 'docker', 'container': 'redis'},
                {'name': 'API', 'kind': 'local', 'command': 'echo ok', 'cwd': self.directory.name},
            ],
        ))
        self.daemon_up = False
        self.refresh_docker_samples()

        pad = self.pad_view(gid)
        self.assertEqual(pad['desired'], 'stopped')
        self.assertEqual(pad['status'], 'stopped')
        docker_components = [c for c in pad['components'] if c['kind'] == 'docker']
        self.assertEqual([c['status'] for c in docker_components], ['unreachable', 'unreachable'])
        self.assertTrue(all('Docker 데몬' in c['error'] for c in docker_components))

    def test_group_start_failure_keeps_desired_stopped(self):
        gid = self.engine.save_pad(PadInput(
            name='Maru Dev',
            slot=0,
            components=[
                {'name': 'PostgreSQL', 'kind': 'docker', 'container': 'pg'},
                {'name': 'API', 'kind': 'local', 'command': 'echo ok', 'cwd': self.directory.name},
            ],
        ))
        self.daemon_up = False
        self.refresh_docker_samples()

        with self.assertRaises(ValueError):
            self.engine.group_action(gid, 'start')

        pad = self.pad_view(gid)
        self.assertEqual(pad['desired'], 'stopped')
        self.assertEqual(pad['status'], 'stopped')

    def test_running_group_shows_unreachable_when_daemon_drops_and_recovers_on_stop(self):
        gid = self.engine.save_pad(PadInput(
            name='Stack',
            slot=0,
            components=[
                {'name': 'PostgreSQL', 'kind': 'docker', 'container': 'pg'},
                {'name': 'Redis', 'kind': 'docker', 'container': 'redis'},
            ],
        ))
        self.engine.group_action(gid, 'start')
        self.refresh_docker_samples()
        pad = self.pad_view(gid)
        self.assertEqual(pad['desired'], 'running')
        self.assertEqual(pad['status'], 'running')

        self.daemon_up = False
        self.refresh_docker_samples()
        pad = self.pad_view(gid)
        self.assertEqual(pad['desired'], 'running')
        self.assertEqual(pad['status'], 'unreachable')

        with self.assertRaises(ValueError):
            self.engine.group_action(gid, 'stop')
        pad = self.pad_view(gid)
        self.assertEqual(pad['desired'], 'stopped')
        self.assertEqual(pad['status'], 'stopped')

    def test_single_docker_pad_follows_same_desired_rule(self):
        pid = self.engine.save_pad(PadInput(
            name='DB',
            slot=0,
            components=[{'name': 'PostgreSQL', 'kind': 'docker', 'container': 'pg'}],
        ))
        self.daemon_up = False
        self.refresh_docker_samples()
        pad = self.pad_view(pid)
        self.assertEqual(pad['desired'], 'stopped')
        self.assertEqual(pad['status'], 'stopped')
        self.assertEqual(pad['components'][0]['status'], 'unreachable')

        self.daemon_up = True
        self.engine.start(pid)
        self.refresh_docker_samples()
        self.assertEqual(self.pad_view(pid)['status'], 'running')

        self.daemon_up = False
        self.refresh_docker_samples()
        self.assertEqual(self.pad_view(pid)['status'], 'unreachable')

        with self.assertRaises(ValueError):
            self.engine.stop(pid)
        self.assertEqual(self.pad_view(pid)['desired'], 'stopped')
        self.assertEqual(self.pad_view(pid)['status'], 'stopped')

    def test_stopped_desired_still_surfaces_active_external_and_conflict(self):
        self.assertEqual(pad_status([{'status': 'running', 'active': True}, {'status': 'stopped', 'active': False}], 'stopped'), 'partial')
        self.assertEqual(pad_status([{'status': 'running', 'active': True}, {'status': 'unreachable', 'active': False}], 'stopped'), 'unhealthy')
        self.assertEqual(pad_status([{'status': 'external', 'active': False}, {'status': 'unreachable', 'active': False}], 'stopped'), 'external')
        self.assertEqual(pad_status([{'status': 'conflict', 'active': False}, {'status': 'stopped', 'active': False}], 'stopped'), 'conflict')

    def test_engine_restart_resets_unowned_desired_to_stopped(self):
        gid = self.engine.save_pad(PadInput(
            name='Stack',
            slot=0,
            components=[
                {'name': 'PostgreSQL', 'kind': 'docker', 'container': 'pg'},
                {'name': 'Redis', 'kind': 'docker', 'container': 'redis'},
            ],
        ))
        self.engine.group_action(gid, 'start')
        self.assertEqual(self.engine.pad_desired_state(gid), 'running')

        restarted = Engine(self.directory.name)
        self.assertEqual(restarted.pad_desired_state(gid), 'stopped')


if __name__ == '__main__':
    unittest.main()
