import copy
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from engine import Engine, ServiceInput
from groups import PadInput


class PadRegistrationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.engine = Engine(self.directory.name)

    def values(self, count=2, slot=0):
        return {'name': 'App', 'slot': slot, 'color': '#3b82f6', 'autostart': False, 'wait_ready': True, 'components': [{'name': name, 'command': 'echo test', 'cwd': self.directory.name} for name in ['Backend', 'Frontend'][:count]]}

    def test_multi_service_registration_shared_color(self):
        pad_id = self.engine.save_pad(PadInput(**self.values()))
        group = self.engine.group(pad_id)
        self.assertEqual(len(group['member_ids']), 2)
        self.assertTrue(group['wait_ready'])
        for sid in group['member_ids']:
            self.assertEqual(self.engine.service(sid)['color'], group['color'])
            self.assertEqual(self.engine.service(sid)['slot'], group['slot'])

    def test_single_service_and_upgrade_keep_log_id(self):
        values = self.values(1)
        pad_id = self.engine.save_pad(PadInput(**values))
        self.assertEqual(self.engine.service(pad_id)['name'], 'App')
        values = self.values()
        values['components'][0]['id'] = pad_id
        group_id = self.engine.save_pad(PadInput(**values), pad_id)
        self.assertIn(pad_id, self.engine.group(group_id)['member_ids'])
        self.assertEqual(len(self.engine.config['services']), 2)

    def test_group_edit_add_remove_and_downgrade(self):
        values = self.values()
        group_id = self.engine.save_pad(PadInput(**values))
        old_ids = self.engine.group(group_id)['member_ids'][:]
        for component, sid in zip(values['components'], old_ids):
            component['id'] = sid
        values['color'] = '#f97316'
        values['components'].append({'name': 'Worker', 'command': 'echo worker', 'cwd': self.directory.name})
        self.assertEqual(self.engine.save_pad(PadInput(**values), group_id), group_id)
        self.assertEqual(self.engine.group(group_id)['member_ids'][:2], old_ids)
        self.assertTrue(all(s['color'] == '#f97316' for s in self.engine.config['services']))
        values['components'] = values['components'][:1]
        self.engine.logs.joinpath(f'{old_ids[1]}.log').write_text('Preserved', encoding='utf-8')
        remaining = self.engine.save_pad(PadInput(**values), group_id)
        self.assertEqual(remaining, old_ids[0])
        self.assertEqual(self.engine.config['groups'], [])
        self.assertEqual(len(self.engine.config['services']), 1)
        self.assertTrue(self.engine.logs.joinpath(f'{old_ids[1]}.log').exists())

    def test_invalid_component_registration_is_atomic(self):
        before = copy.deepcopy(self.engine.config)
        values = self.values()
        values['components'][1]['cwd'] = str(Path(self.directory.name) / 'missing')
        with self.assertRaises(ValueError):
            self.engine.save_pad(PadInput(**values))
        self.assertEqual(self.engine.config, before)
        self.assertFalse(self.engine.path.exists())

    def test_edit_cannot_claim_another_pad_component(self):
        pad_id = self.engine.save_pad(PadInput(**self.values(1)))
        other = self.engine.save_pad(PadInput(**self.values(1, 1)))
        before = copy.deepcopy(self.engine.config)
        values = self.values()
        values['components'][0]['id'] = pad_id
        values['components'][1]['id'] = other
        with self.assertRaises(ValueError):
            self.engine.save_pad(PadInput(**values), pad_id)
        self.assertEqual(self.engine.config, before)

    def test_running_group_can_move_without_runtime_change(self):
        pad_id = self.engine.save_pad(PadInput(**self.values()))
        for service in self.engine.config['services']:
            service['runtime'] = {'pid': 1234, 'created': 100.0}
        before = copy.deepcopy(self.engine.config)
        with patch.object(self.engine, 'owned', return_value=object()):
            self.engine.move_pad(pad_id, 7)
            with self.assertRaises(ValueError):
                self.engine.save_pad(PadInput(**self.values()), pad_id)
            with self.assertRaises(ValueError):
                self.engine.delete_pad(pad_id)
        self.assertEqual(self.engine.group(pad_id)['slot'], 7)
        for original, updated in zip(before['services'], self.engine.config['services']):
            self.assertEqual({k: v for k, v in original.items() if k != 'slot'}, {k: v for k, v in updated.items() if k != 'slot'})
            self.assertEqual(updated['slot'], 7)

    def test_move_occupied_slot_and_member_only_move_rejected(self):
        pad_id = self.engine.save_pad(PadInput(**self.values()))
        self.engine.save_pad(PadInput(**self.values(1, 1)))
        before = copy.deepcopy(self.engine.config)
        with self.assertRaises(ValueError):
            self.engine.move_pad(pad_id, 1)
        with self.assertRaises(ValueError):
            self.engine.move_pad(self.engine.group(pad_id)['member_ids'][0], 2)
        self.assertEqual(self.engine.config, before)

    def test_save_failure_rolls_back_memory_and_disk(self):
        pad_id = self.engine.save_pad(PadInput(**self.values()))
        before = copy.deepcopy(self.engine.config)
        disk = self.engine.path.read_bytes()
        with patch.object(self.engine, 'save', side_effect=OSError('Storage unavailable')):
            with self.assertRaises(OSError):
                self.engine.move_pad(pad_id, 5)
            with self.assertRaises(OSError):
                self.engine.save_pad(PadInput(**self.values(1, 5)))
        self.assertEqual(self.engine.config, before)
        self.assertEqual(self.engine.path.read_bytes(), disk)

    def test_component_color_follows_shared_color(self):
        pad_id = self.engine.save_pad(PadInput(**self.values()))
        sid = self.engine.group(pad_id)['member_ids'][0]
        self.engine.add(ServiceInput(name='Backend', command='echo changed', cwd=self.directory.name, slot=0, color='#eea0c7'), sid)
        self.assertEqual(self.engine.service(sid)['color'], '#3b82f6')

    def test_two_moves_to_same_target_have_one_winner(self):
        ids = [self.engine.save_pad(PadInput(**self.values(1, slot))) for slot in (0, 1)]
        barrier = threading.Barrier(2)
        outcomes = []
        def move(sid):
            barrier.wait()
            try:
                self.engine.move_pad(sid, 5)
                outcomes.append('moved')
            except ValueError:
                outcomes.append('occupied')
        threads = [threading.Thread(target=move, args=(sid,)) for sid in ids]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=5)
        self.assertCountEqual(outcomes, ['moved', 'occupied'])
        self.assertEqual(sum(s['slot'] == 5 for s in self.engine.config['services']), 1)

    def test_delete_group_preserves_logs(self):
        pad_id = self.engine.save_pad(PadInput(**self.values()))
        ids = self.engine.group(pad_id)['member_ids'][:]
        for sid in ids:
            self.engine.logs.joinpath(f'{sid}.log').write_text('History', encoding='utf-8')
        self.engine.delete_pad(pad_id)
        self.assertEqual(self.engine.config['services'], [])
        self.assertEqual(self.engine.config['groups'], [])
        self.assertTrue(all(self.engine.logs.joinpath(f'{sid}.log').exists() for sid in ids))


if __name__ == '__main__':
    unittest.main()
