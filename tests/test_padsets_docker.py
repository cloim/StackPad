import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from engine import Engine, ServiceInput
from groups import GroupInput, PadInput
from padsets import PadsetInput
from docker_services import DockerServiceInput, docker_cli


class PadsetTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.engine = Engine(self.directory.name)

    def pad(self, slot=0, padset='default', count=1):
        return PadInput(name='앱', slot=slot, padset_id=padset, components=[{'name': str(i), 'command': 'echo test', 'cwd': self.directory.name} for i in range(count)])

    def test_sixteen_independent_slots_and_reopen(self):
        second = self.engine.save_padset(PadsetInput(name='개발'))
        for slot in range(16):
            self.engine.save_pad(self.pad(slot))
            self.engine.save_pad(self.pad(slot, second))
        self.assertEqual(len(self.engine.config['services']), 32)
        with self.assertRaises(ValueError):
            self.engine.save_pad(self.pad(0, second))
        restored = Engine(self.directory.name)
        self.assertEqual(len(restored.config['padsets']), 2)
        self.assertEqual(len(restored.config['services']), 32)

    def test_migrates_existing_group_and_services(self):
        gid = self.engine.save_pad(self.pad(count=2))
        data = self.engine.config
        del data['padsets']
        for p in [*data['services'], *data['groups']]:
            del p['padset_id']
        self.engine.save()
        restored = Engine(self.directory.name)
        self.assertEqual(restored.group(gid)['padset_id'], 'default')
        self.assertTrue(all(s['padset_id'] == 'default' for s in restored.config['services']))
        self.assertTrue(all(s['command'] == 'echo test' for s in restored.config['services']))

    def test_move_group_and_slot_collisions_are_scoped(self):
        second = self.engine.save_padset(PadsetInput(name='개발'))
        gid = self.engine.save_pad(self.pad(count=2))
        other = self.engine.save_pad(self.pad(padset=second))
        with self.assertRaises(ValueError):
            self.engine.move_pad(gid, 0, second)
        self.engine.move_pad(gid, 1, second)
        self.assertTrue(all(self.engine.service(sid)['padset_id'] == second for sid in self.engine.group(gid)['member_ids']))
        self.assertEqual(self.engine.group(gid)['padset_id'], second)
        self.engine.dissolve_group(gid)
        self.assertEqual(sorted(s['slot'] for s in self.engine.config['services']), [0, 1, 2])
        self.assertEqual(self.engine.service(other)['slot'], 0)

    def test_edit_move_and_invalid_set_leave_original(self):
        second = self.engine.save_padset(PadsetInput(name='개발'))
        pid = self.engine.save_pad(self.pad())
        values = self.pad(15, second)
        values.components[0].id = pid
        self.engine.save_pad(values, pid)
        self.assertEqual(self.engine.service(pid)['padset_id'], second)
        with self.assertRaises(ValueError):
            self.engine.save_pad(self.pad(padset='missing'))
        self.assertEqual(len(self.engine.config['services']), 1)
        with self.assertRaises(ValueError):
            self.engine.delete_padset(second)
        self.engine.delete_padset('default')
        with self.assertRaises(ValueError):
            self.engine.delete_padset(second)

    def test_set_name_and_legacy_service_slot_guard(self):
        second = self.engine.save_padset(PadsetInput(name='개발'))
        self.engine.save_pad(self.pad())
        values = ServiceInput(name='단독', command='echo test', cwd=self.directory.name, slot=0, padset_id=second)
        self.engine.add(values)
        with self.assertRaises(ValueError):
            self.engine.add(values)
        self.engine.save_padset(PadsetInput(name='운영'), second)
        with self.assertRaises(ValueError):
            self.engine.save_padset(PadsetInput(name='운영'))


class DockerTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.engine = Engine(self.directory.name)
        self.running = False
        self.health = 'healthy'
        self.commands = []
        self.mock = patch('docker_services.docker_cli', side_effect=self.cli)
        self.mock.start()
        self.addCleanup(self.mock.stop)

    def cli(self, *args):
        self.commands.append(args)
        if args[0] == 'inspect':
            if args[2] == '{{.Id}}':
                return 'a' * 64 + '\n'
            return json.dumps({'state': {'Running': self.running, 'ExitCode': 0, 'Health': {'Status': self.health}, 'StartedAt': '2026-10-12T00:00:00Z'}, 'name': '/test-api', 'ports': {'5432/tcp': [{'HostIp': '0.0.0.0', 'HostPort': '47000'}, {'HostIp': '::', 'HostPort': '47000'}], '6379/tcp': None}})
        if args[0] == 'start':
            self.running = True
        elif args[0] == 'stop':
            self.running = False
        elif args[0] == 'logs':
            return 'ready\n'
        elif args[0] == 'ls':
            return json.dumps({'ID': 'a' * 64, 'Names': 'test-api', 'Image': 'nginx', 'Status': 'Up'})
        return ''

    def register(self):
        return self.engine.save_pad(PadInput(name='컨테이너', slot=0, components=[{'name': '웹', 'kind': 'docker', 'container': 'test-api'}]))

    def test_register_start_health_stop_logs_and_delete_only_registration(self):
        pid = self.register()
        self.assertEqual(self.engine.service(pid)['container'], 'a' * 64)
        self.engine.start(pid)
        self.assertTrue(self.engine.active(pid))
        self.assertEqual(self.engine.snapshot()[0]['status'], 'running')
        self.health = 'unhealthy'
        self.assertEqual(self.engine.status_of(pid), 'unhealthy')
        with self.assertRaises(ValueError):
            self.engine.delete_pad(pid)
        with patch('engine.docker_cli', side_effect=self.cli):
            self.assertEqual(self.engine.tail(pid), 'ready\n')
        self.engine.stop(pid)
        self.engine.delete_pad(pid)
        self.assertFalse(any(cmd[0] == 'rm' for cmd in self.commands))

    def test_duplicate_alias_and_busy_edit_guard(self):
        pid = self.register()
        with self.assertRaises(ValueError):
            self.engine.save_pad(PadInput(name='중복', slot=1, components=[{'name': '웹', 'kind': 'docker', 'container': 'alias'}]))
        self.engine.docker_busy.add(pid)
        with self.assertRaises(ValueError):
            self.engine.delete_pad(pid)
        self.assertEqual(len(self.engine.config['services']), 1)

    def test_discovery_and_unavailable(self):
        state = self.engine.docker_state({'container': 'test-api'})
        self.assertEqual(state['container_name'], 'test-api')
        self.assertEqual(state['container_ports'], ['47000', '6379'])
        self.assertEqual(self.engine.docker_containers()[0]['name'], 'test-api')
        with patch('docker_services.docker_cli', side_effect=ValueError('offline')):
            self.assertEqual(self.engine.docker_state({'container': 'test-api'})['status'], 'unreachable')

    def test_cli_uses_argument_array_and_blocks_stdin(self):
        with patch('docker_services.subprocess.run', return_value=subprocess.CompletedProcess([], 0, 'ok', '')) as run:
            self.assertEqual(docker_cli('start', 'test-api'), 'ok')
            self.assertEqual(run.call_args.args[0], ['docker', 'container', 'start', 'test-api'])
            self.assertEqual(run.call_args.kwargs['stdin'], subprocess.DEVNULL)
            self.assertNotIn('shell', run.call_args.kwargs)
        for target in ('--help', 'x & calc', 'x\nname'):
            with self.assertRaises(ValueError):
                DockerServiceInput(name='웹', container=target, slot=0)


if __name__ == '__main__':
    unittest.main()
