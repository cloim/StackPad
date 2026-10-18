import sys
import tempfile
import unittest
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from engine import Engine
from main import create_app
from auth_helper import OWNER, sign_in


class AlertsTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.data = Path(self.folder.name)
        self.app = create_app(self.data, self.data)
        self.engine = self.app.state.engine
        self.transport = httpx.ASGITransport(app=self.app, client=('127.0.0.1', 50000))
        self.client = httpx.AsyncClient(transport=self.transport, base_url='http://127.0.0.1')
        sign_in(self.app, self.client)

    async def asyncTearDown(self):
        await self.client.aclose()
        self.engine.closed.set()
        self.engine.wake.set()

    def test_alert_recording_and_notification_filtering(self):
        published = []
        hub = self.engine.events
        original_pub = hub.publish

        def track(topic, data):
            if topic == 'alert':
                published.append(data)
            return original_pub(topic, data)

        hub.publish = track

        # 1. Default notifications (all True)
        self.engine.record_alert('p1', 'Pad1', 'crashed', 'Process crashed')
        self.assertEqual(len(self.engine.alerts), 1)
        self.assertEqual(len(published), 1)
        self.assertEqual(published[0]['kind'], 'crashed')

        # 2. Disable crash notifications
        self.engine.config['notifications'] = {'crash': False, 'unhealthy': True, 'schedule': True}
        self.engine.record_alert('p1', 'Pad1', 'restarted', 'Restarting 1/3')
        # Kept in alerts deque:
        self.assertEqual(len(self.engine.alerts), 2)
        # But NOT published:
        self.assertEqual(len(published), 1)

        # 3. Unhealthy is still enabled -> published
        self.engine.record_alert('p2', 'Pad2', 'unhealthy', 'Unhealthy detected')
        self.assertEqual(len(self.engine.alerts), 3)
        self.assertEqual(len(published), 2)
        self.assertEqual(published[1]['kind'], 'unhealthy')

    async def test_alerts_api_and_after_filter(self):
        # Record 4 alerts
        for i in range(1, 5):
            self.engine.record_alert(f'p{i}', f'Pad{i}', 'crashed', f'Msg {i}')

        # 1. Fetch all alerts
        res = await self.client.get('/api/alerts')
        self.assertEqual(res.status_code, 200)
        data = res.json()['alerts']
        self.assertEqual(len(data), 4)
        self.assertEqual([a['id'] for a in data], [1, 2, 3, 4])

        # 2. Fetch with after=2
        res2 = await self.client.get('/api/alerts?after=2')
        self.assertEqual(res2.status_code, 200)
        data2 = res2.json()['alerts']
        self.assertEqual(len(data2), 2)
        self.assertEqual([a['id'] for a in data2], [3, 4])

    async def test_update_notifications_settings_api(self):
        res = await self.client.put('/api/settings/notifications', json={
            'crash': False,
            'unhealthy': True,
            'schedule': False,
        }, headers={'Origin': 'http://127.0.0.1'})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()['notifications'], {
            'crash': False,
            'unhealthy': True,
            'schedule': False,
        })
        self.assertEqual(self.engine.config['notifications']['crash'], False)


if __name__ == '__main__':
    unittest.main()
