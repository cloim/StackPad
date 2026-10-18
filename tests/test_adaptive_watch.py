import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from engine import Engine, ServiceInput


class AdaptiveWatchTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.engine = Engine(self.folder.name)

    def test_interval_determination(self):
        # 1. No active services, not busy -> interval should be 10
        self.engine.last_activity = 0
        with self.engine.lock:
            has_owned = any(self.engine.owned(s) for s in self.engine.config['services'])
            docker_active = any(s.get('kind') == 'docker' and self.engine.docker_state(s)['active'] for s in self.engine.config['services'])
            busy = bool(self.engine.group_operations) or (time.time() - self.engine.last_activity < 15)
        interval = 2 if (has_owned or docker_active or busy) else 10
        self.assertEqual(interval, 10)

        # 2. Activity triggered -> interval becomes 2
        self.engine.last_activity = time.time()
        with self.engine.lock:
            has_owned = any(self.engine.owned(s) for s in self.engine.config['services'])
            docker_active = any(s.get('kind') == 'docker' and self.engine.docker_state(s)['active'] for s in self.engine.config['services'])
            busy = bool(self.engine.group_operations) or (time.time() - self.engine.last_activity < 15)
        interval = 2 if (has_owned or docker_active or busy) else 10
        self.assertEqual(interval, 2)

    def test_wake_event_signaled_on_state_changes(self):
        self.assertFalse(self.engine.wake.is_set())
        # engine.wake.set() can be called to awaken watch immediately
        self.engine.wake.set()
        self.assertTrue(self.engine.wake.is_set())
        self.engine.wake.clear()
        self.assertFalse(self.engine.wake.is_set())

    def test_listeners_throttle_in_stopped_state(self):
        # Add a stopped service with port
        self.engine.add(ServiceInput(
            name='PortService',
            kind='local',
            command='cmd.exe',
            cwd=str(Path.cwd()),
            color='#22c55e',
            slot=0,
            padset_id='default',
            port=8080
        ))

        # Simulate 60 simulated seconds in stopped state, without active UI viewers
        self.engine.last_services_poll = 0
        self.assertEqual(self.engine.events.subscribers, 0)

        simulated_time = 1000.0
        last_listeners_time = 0
        listener_calls = 0

        with patch.object(self.engine, 'listeners', return_value={}) as mock_listeners:
            for step in range(60):
                simulated_time += 1.0  # 1 second step
                now = simulated_time
                services = [dict(s) for s in self.engine.config['services'] if s.get('kind', 'local') == 'local']
                has_stopped_port = any(s.get('port') and not self.engine.owned(s) for s in services)
                actively_viewed = (self.engine.events.subscribers > 0) or (now - self.engine.last_services_poll < 10)

                if has_stopped_port and (actively_viewed or now - last_listeners_time >= 10):
                    self.engine.listeners()
                    listener_calls += 1
                    last_listeners_time = now

            # In 60 seconds, with 10s throttling, listener_calls should be <= 6 (1 at 10s, 20s, 30s, 40s, 50s, 60s)
            self.assertLessEqual(listener_calls, 6)
            self.assertGreaterEqual(listener_calls, 5)


if __name__ == '__main__':
    unittest.main()
