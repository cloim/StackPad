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

    def test_running_metadata_edit_preserves_runtime_samples_and_history(self):
        for count in (1, 2):
            with self.subTest(count=count):
                values = self.values(count, slot=count + 4)
                pad_id = self.engine.save_pad(PadInput(**values))
                ids = self.engine.group(pad_id)['member_ids'] if count > 1 else [pad_id]
                for component, sid in zip(values['components'], ids):
                    component['id'] = sid
                    self.engine.service(sid)['runtime'] = {'pid': 1234, 'created': 100.0}
                    self.engine.samples[sid] = {'status': 'running', 'cpu': 12}
                    self.engine.restarts[sid] = {'attempts': [10], 'next_at': 0}
                    component.update(name='Renamed component', health_url='http://localhost:8000/health', restart_policy='on-failure', restart_max=7)
                values.update(name='Renamed pad', environment='production', color='#a855f7', autostart=True, wait_ready=False, domain_url='https://app.example.com/', local_url='http://localhost:8000/')
                samples, restarts = copy.deepcopy(self.engine.samples), copy.deepcopy(self.engine.restarts)
                with patch.object(self.engine, 'owned', return_value=object()):
                    self.assertEqual(self.engine.save_pad(PadInput(**values), pad_id), pad_id)
                target = self.engine.group(pad_id) if count > 1 else self.engine.service(pad_id)
                self.assertEqual(target['environment'], 'production')
                self.assertEqual(target['name'], 'Renamed pad')
                for sid in ids:
                    service = self.engine.service(sid)
                    self.assertEqual(service['runtime'], {'pid': 1234, 'created': 100.0})
                    self.assertEqual(service['restart_max'], 7)
                    self.assertEqual(service['health_url'], 'http://localhost:8000/health')
                self.assertEqual(self.engine.samples, samples)
                self.assertEqual(self.engine.restarts, restarts)
                loaded = Engine(self.directory.name)
                self.assertEqual((loaded.group(pad_id) if count > 1 else loaded.service(pad_id))['environment'], 'production')

    def test_running_execution_changes_and_structure_are_rejected_atomically(self):
        values = self.values()
        pad_id = self.engine.save_pad(PadInput(**values))
        for component, sid in zip(values['components'], self.engine.group(pad_id)['member_ids']):
            component['id'] = sid
        before = copy.deepcopy(self.engine.config)
        candidates = []
        for key, value in [('command', 'echo changed'), ('port', 9000), ('cwd', str(Path(self.directory.name).parent)), ('kind', 'docker')]:
            changed = copy.deepcopy(values)
            changed['components'][0][key] = value
            candidates.append(changed)
        for components in [values['components'][::-1], values['components'][:1], values['components'] + [self.values(1)['components'][0]]]:
            candidates.append({**values, 'components': components})
        with patch.object(self.engine, 'owned', return_value=object()):
            for changed in candidates:
                with self.subTest(changed=changed), self.assertRaises(ValueError):
                    self.engine.save_pad(PadInput(**changed), pad_id)
                self.assertEqual(self.engine.config, before)
            with patch.object(self.engine, 'save', side_effect=OSError('disk full')):
                with self.assertRaises(OSError):
                    self.engine.save_pad(PadInput(**{**values, 'environment': 'production'}), pad_id)
            self.assertEqual(self.engine.config, before)

    def test_metadata_only_protects_stopped_execution_and_environment_validation(self):
        values = self.values(1)
        pad_id = self.engine.save_pad(PadInput(**values))
        values['components'][0]['id'] = pad_id
        values['environment'] = 'production'
        self.engine.save_pad(PadInput(**values), pad_id, metadata_only=True)
        values['components'][0]['command'] = 'echo changed'
        with self.assertRaises(ValueError):
            self.engine.save_pad(PadInput(**values), pad_id, metadata_only=True)
        with self.assertRaises(ValueError):
            PadInput(**{**values, 'environment': 'invalid'})

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
