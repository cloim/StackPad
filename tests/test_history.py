import tempfile
import unittest
from pathlib import Path
from collections import deque
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from engine import Engine


class HistoryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.engine = Engine(self.tmp.name)
        self.engine.monitor = None

    def tearDown(self):
        self.engine.closed.set()
        self.tmp.cleanup()

    def test_local_service_history(self):
        sid = 'srv1'
        self.engine.config['services'].append({
            'id': sid,
            'name': 'API',
            'kind': 'local',
            'command': 'cmd',
            'cwd': self.tmp.name,
            'slot': 0,
            'padset_id': 'default'
        })
        # Empty initially
        res = self.engine.service_history(sid)
        self.assertEqual(res, {'interval': 10, 'cpu': [], 'memory': []})

        # Inject history
        self.engine.history[sid] = deque([(12.5, 45.0), (25.0, 50.0)], maxlen=60)
        res = self.engine.service_history(sid)
        self.assertEqual(res['interval'], 10)
        self.assertEqual(res['cpu'], [12.5, 25.0])
        self.assertEqual(res['memory'], [45.0, 50.0])

    def test_group_history_sums_members(self):
        s1 = 'srv1'
        s2 = 'srv2'
        self.engine.config['services'].extend([
            {'id': s1, 'name': 'A', 'kind': 'local', 'command': 'cmd', 'cwd': self.tmp.name, 'slot': 0, 'padset_id': 'default'},
            {'id': s2, 'name': 'B', 'kind': 'local', 'command': 'cmd', 'cwd': self.tmp.name, 'slot': 0, 'padset_id': 'default'}
        ])
        gid = 'group1'
        self.engine.config['groups'] = [{
            'id': gid,
            'name': 'FullStack',
            'member_ids': [s1, s2],
            'slot': 0,
            'padset_id': 'default'
        }]

        self.engine.history[s1] = deque([(10.0, 100.0), (20.0, 120.0)], maxlen=60)
        self.engine.history[s2] = deque([(5.0, 50.0), (15.0, 60.0)], maxlen=60)

        res = self.engine.service_history(gid)
        self.assertEqual(res['interval'], 10)
        self.assertEqual(res['cpu'], [15.0, 35.0])
        self.assertEqual(res['memory'], [150.0, 180.0])

    def test_docker_and_remote_empty(self):
        did = 'doc1'
        self.engine.config['services'].append({
            'id': did,
            'name': 'Docker',
            'kind': 'docker',
            'container': 'c1',
            'slot': 0,
            'padset_id': 'default'
        })
        res = self.engine.service_history(did)
        self.assertEqual(res, {'interval': 10, 'cpu': [], 'memory': []})

    def test_not_found(self):
        with self.assertRaises(KeyError):
            self.engine.service_history('nonexistent')


if __name__ == '__main__':
    unittest.main()
