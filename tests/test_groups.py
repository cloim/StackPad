import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from engine import Engine, ServiceInput
from groups import GroupInput


class GroupTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.engine = Engine(self.folder.name)
        self.ids = [self.engine.add(ServiceInput(name=name, command='echo test', cwd=self.folder.name, slot=i)) for i, name in enumerate(['Backend', 'Frontend', 'Other'])]
        self.active = set()
        self.actions = []
        self.fail_id = None
        self.patchers = [patch.object(self.engine, 'owned', side_effect=lambda s: object() if s['id'] in self.active else None), patch.object(self.engine, 'start', side_effect=self.start), patch.object(self.engine, 'stop', side_effect=self.stop)]
        for patcher in self.patchers:
            patcher.start()
            self.addCleanup(patcher.stop)
        self.group_id = self.engine.save_group(GroupInput(name='App', member_ids=self.ids[:2], slot=0))

    def start(self, sid, takeover=False):
        self.actions.append(('start', sid))
        if sid == self.fail_id:
            raise ValueError('Start failed')
        self.active.add(sid)
        self.engine.samples[sid] = {'status': 'running'}

    def stop(self, sid):
        self.actions.append(('stop', sid))
        self.active.discard(sid)

    def test_persistence_and_freed_pad(self):
        loaded = Engine(self.folder.name)
        self.assertEqual(loaded.group(self.group_id)['member_ids'], self.ids[:2])
        self.assertEqual([loaded.service(s)['slot'] for s in self.ids], [0, 0, 2])
        loaded.add(ServiceInput(name='New', command='echo new', cwd=self.folder.name, slot=1))
        with self.assertRaises(ValueError):
            loaded.add(ServiceInput(name='Occupied', command='echo new', cwd=self.folder.name, slot=0))

    def test_extended_pad_colors(self):
        for color in ('#25bfd0', '#a8bbe6', '#f5f5f4'):
            ServiceInput(name='Color', command='echo test', cwd=self.folder.name, slot=5, color=color)
            GroupInput(name='Color', member_ids=self.ids[:2], slot=0, color=color)
        with self.assertRaises(ValueError):
            ServiceInput(name='Color', command='echo test', cwd=self.folder.name, slot=5, color='#123456')

    def test_running_pad_recolor_preserves_runtime_and_commands(self):
        import copy
        self.active.update(self.ids)
        self.engine.service(self.ids[0])['runtime'] = {'pid': 12345, 'created': 1.0}
        before = copy.deepcopy(self.engine.config)
        self.engine.set_pad_color(self.group_id, '#a855f7')
        self.engine.set_pad_color(self.ids[2], '#3b82f6')
        for service in self.engine.config['services']:
            old = next(s for s in before['services'] if s['id'] == service['id'])
            self.assertEqual({k:v for k,v in service.items() if k != 'color'}, {k:v for k,v in old.items() if k != 'color'})
        self.assertEqual(self.engine.group(self.group_id)['color'], '#a855f7')
        self.assertEqual([self.engine.service(sid)['color'] for sid in self.ids], ['#a855f7','#a855f7','#3b82f6'])
        self.assertEqual(self.active, set(self.ids))
        self.assertEqual(self.actions, [])
        self.assertEqual(Engine(self.folder.name).group(self.group_id)['color'], '#a855f7')
        with self.assertRaises(ValueError):
            self.engine.set_pad_color(self.group_id, '#123456')

    def test_recolor_rolls_back_when_save_fails(self):
        import copy
        before = copy.deepcopy(self.engine.config)
        with patch.object(self.engine, 'save', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                self.engine.set_pad_color(self.group_id, '#a855f7')
        self.assertEqual(self.engine.config, before)

    def test_earlier_palette_colors_are_migrated(self):
        self.engine.service(self.ids[2])['color'] = '#f2ad62'
        self.engine.group(self.group_id)['color'] = '#a77bd9'
        self.engine.save()
        loaded = Engine(self.folder.name)
        self.assertEqual(loaded.service(self.ids[2])['color'], '#f97316')
        self.assertEqual(loaded.group(self.group_id)['color'], '#a855f7')
        self.assertEqual(Engine(self.folder.name).service(self.ids[2])['color'], '#f97316', 'Migration is saved')

    def test_grouped_service_edit_and_delete(self):
        self.engine.add(ServiceInput(name='Renamed', command='echo edit', cwd=self.folder.name, slot=0), self.ids[0])
        with self.assertRaises(ValueError):
            self.engine.delete(self.ids[0])
        with self.assertRaises(ValueError):
            self.engine.add(ServiceInput(name='Moved', command='echo edit', cwd=self.folder.name, slot=4), self.ids[0])

    def test_start_order_and_reverse_stop(self):
        self.engine.group_action(self.group_id, 'start')
        self.engine.group_action(self.group_id, 'stop')
        self.assertEqual(self.actions, [('start', self.ids[0]), ('start', self.ids[1]), ('stop', self.ids[1]), ('stop', self.ids[0])])
        self.assertEqual(self.engine.group_operations, {})

    def test_failure_rolls_back_new_members(self):
        self.fail_id = self.ids[1]
        with self.assertRaises(ValueError):
            self.engine.group_action(self.group_id, 'start')
        self.assertFalse(self.active)
        self.assertEqual(self.actions[-1], ('stop', self.ids[0]))

    def test_existing_member_preserved_on_failure(self):
        self.active.add(self.ids[0])
        self.fail_id = self.ids[1]
        with self.assertRaises(ValueError):
            self.engine.group_action(self.group_id, 'start')
        self.assertEqual(self.active, {self.ids[0]})
        self.assertEqual(self.actions, [('start', self.ids[1])])

    def test_readiness_timeout_rolls_back(self):
        self.engine.group(self.group_id)['wait_ready'] = True
        def pending(sid, takeover=False):
            self.active.add(sid)
        with patch.object(self.engine, 'start', side_effect=pending), patch('groups.time.monotonic', side_effect=[0, 31]):
            with self.assertRaisesRegex(ValueError, '준비 확인'):
                self.engine.group_action(self.group_id, 'start')
        self.assertFalse(self.active)
        self.assertEqual(self.actions, [('stop', self.ids[0])])

    def test_ready_member_allows_next_start(self):
        self.engine.group(self.group_id)['wait_ready'] = True
        self.engine.group_action(self.group_id, 'start')
        self.assertEqual(self.active, set(self.ids[:2]))

    def test_health_probe_advances_group_when_sample_is_stale(self):
        self.engine.group(self.group_id)['wait_ready'] = True
        for sid in self.ids[:2]:
            self.engine.service(sid)['health_url'] = 'http://127.0.0.1/health'
        def pending(sid, takeover=False):
            self.actions.append(('start', sid))
            self.active.add(sid)
            self.engine.samples[sid] = {'status': 'starting'}
        with patch.object(self.engine, 'start', side_effect=pending), patch.object(self.engine, 'local_ready', return_value=True):
            self.engine.group_action(self.group_id, 'start')
        self.assertEqual(self.active, set(self.ids[:2]))
        self.assertEqual([self.engine.samples[sid]['status'] for sid in self.ids[:2]], ['running', 'running'])

    def test_stop_continues_after_failure(self):
        def failing(sid):
            self.actions.append(('stop', sid))
            if sid == self.ids[1]:
                raise ValueError('Stop failed')
        with patch.object(self.engine, 'stop', side_effect=failing):
            with self.assertRaises(ValueError):
                self.engine.group_action(self.group_id, 'stop')
        self.assertEqual(self.actions, [('stop', self.ids[1]), ('stop', self.ids[0])])

    def test_duplicate_missing_or_occupied_members_rejected(self):
        with self.assertRaises(ValueError):
            GroupInput(name='Bad', member_ids=[self.ids[0], self.ids[0]], slot=0)
        with self.assertRaises(KeyError):
            self.engine.save_group(GroupInput(name='Bad', member_ids=[self.ids[2], 'missing'], slot=2))
        with self.assertRaises(ValueError):
            self.engine.save_group(GroupInput(name='Bad', member_ids=[self.ids[0], self.ids[2]], slot=0))
        with self.assertRaises(ValueError):
            self.engine.save_group(GroupInput(name='Bad', member_ids=self.ids[:2], slot=2), self.group_id)

    def test_running_group_settings_and_dissolve_guard(self):
        self.active.add(self.ids[0])
        with self.assertRaises(ValueError):
            self.engine.save_group(GroupInput(name='Changed', member_ids=self.ids[:2], slot=0), self.group_id)
        with self.assertRaises(ValueError):
            self.engine.dissolve_group(self.group_id)

    def test_dissolve_preserves_services_and_assigns_free_slots(self):
        self.engine.dissolve_group(self.group_id)
        self.assertEqual(len(self.engine.config['services']), 3)
        self.assertEqual([self.engine.service(s)['slot'] for s in self.ids], [0, 1, 2])
        self.assertEqual(self.engine.config['groups'], [])

    def test_busy_group_rejects_parallel_operations(self):
        self.engine.group_operations[self.ids[0]] = threading.get_ident() + 1
        with self.assertRaises(ValueError):
            self.engine.group_action(self.group_id, 'start')
        with self.assertRaises(ValueError):
            self.engine.dissolve_group(self.group_id)
        with self.assertRaises(ValueError):
            self.engine.add(ServiceInput(name='Changed', command='echo edit', cwd=self.folder.name, slot=0), self.ids[0])

    def test_pad_folder_opens_shared_member_folder_in_code(self):
        root = Path(self.folder.name)
        for name, sid in zip(['backend', 'frontend'], self.ids[:2]):
            (root / name).mkdir()
            self.engine.service(sid)['cwd'] = str(root / name)
        self.assertEqual(self.engine.pad_folder(self.group_id), str(root))
        self.assertEqual(self.engine.pad_folder(self.ids[2]), self.folder.name)
        with patch('engine.vscode_path', return_value='Code.exe'), patch('engine.subprocess.Popen') as popen:
            self.assertEqual(self.engine.open_in_code(self.group_id), str(root))
        self.assertEqual(popen.call_args.args[0], ['Code.exe', str(root)])
        self.engine.service(self.ids[2])['cwd'] = str(root / 'missing')
        with self.assertRaises(ValueError):
            self.engine.pad_folder(self.ids[2])

    def test_group_progress_events(self):
        published = []
        class DummyEvents:
            def publish(self, topic, data):
                if topic == 'progress':
                    published.append(dict(data))
        self.engine.events = DummyEvents()

        self.engine.group_action(self.group_id, 'start')
        phases = [p['phase'] for p in published]
        self.assertEqual(phases, ['starting', 'starting', 'finished'])
        self.assertEqual(published[0]['current_id'], self.ids[0])
        self.assertEqual(published[1]['current_id'], self.ids[1])
        self.assertEqual(published[-1]['done'], 2)

        published.clear()
        self.engine.group_action(self.group_id, 'stop')
        stop_phases = [p['phase'] for p in published]
        self.assertEqual(stop_phases, ['stopping', 'stopping', 'finished'])
        self.assertEqual(published[0]['current_id'], self.ids[1])
        self.assertEqual(published[1]['current_id'], self.ids[0])


if __name__ == '__main__':
    unittest.main()
