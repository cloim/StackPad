import asyncio
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from events import EventHub
from engine import Engine
from main import create_app
from auth_helper import sign_in


class EventHubTests(unittest.IsolatedAsyncioTestCase):
    async def test_publish_and_subscribe(self):
        hub = EventHub()
        received = []

        async def reader():
            async for topic, data in hub.subscribe(['services', 'settings']):
                received.append((topic, data))
                if len(received) == 2:
                    break

        task = asyncio.create_task(reader())
        await asyncio.sleep(0.01)
        self.assertEqual(hub.subscribers, 1)

        hub.publish('services', {'count': 1})
        hub.publish('alert', {'kind': 'ignored'})  # not subscribed
        hub.publish('settings', {'theme': 'dark'})

        await asyncio.wait_for(task, timeout=2.0)
        self.assertEqual(received, [('services', {'count': 1}), ('settings', {'theme': 'dark'})])
        await asyncio.sleep(0.01)
        self.assertEqual(hub.subscribers, 0)

    async def test_queue_overflow_and_services_retention(self):
        hub = EventHub()
        queue, unsub = hub.register()
        try:
            # Publish 70 alerts (maxsize is 64, so oldest should be dropped)
            for i in range(70):
                hub.publish('alert', {'num': i})
            await asyncio.sleep(0.01)

            # Next item read should be num 6 (since 0..5 were dropped when full)
            topic, data = queue.get_nowait()
            self.assertEqual(topic, 'alert')
            self.assertEqual(data['num'], 6)

            # Publish multiple services events
            hub.publish('services', {'v': 1})
            hub.publish('services', {'v': 2})
            hub.publish('services', {'v': 3})
            await asyncio.sleep(0.01)

            # Drain until we see services; only the latest services should exist
            services_data = []
            while not queue.empty():
                item = queue.get_nowait()
                if item[0] == 'services':
                    services_data.append(item[1])

            self.assertEqual(services_data, [{'v': 3}])
        finally:
            unsub()


class EngineNotifyServicesTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.engine = Engine(self.folder.name)

    def test_hash_duplicate_suppression(self):
        published = []
        hub = self.engine.events
        original_publish = hub.publish

        def track(topic, data):
            published.append((topic, data))
            return original_publish(topic, data)

        with patch.object(hub, 'publish', side_effect=track):
            self.engine.notify_services()
            self.assertEqual(len(published), 1)
            self.assertEqual(published[0][0], 'services')

            # Calling again with identical state must NOT publish
            self.engine.notify_services()
            self.assertEqual(len(published), 1)

            # Modifying state should trigger new publish
            self.engine.config['services'].append({
                'id': 'test-pad-id',
                'name': 'Test',
                'kind': 'local',
                'command': 'cmd.exe',
                'cwd': str(Path.cwd()),
                'color': '#22c55e',
                'slot': 0,
                'padset_id': 'default'
            })
            self.engine.notify_services()
            self.assertEqual(len(published), 2)


class EventsApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.data = Path(self.folder.name)
        self.app = create_app(self.data, self.data)

        # Sign in client
        from auth_helper import OWNER
        google = self.app.state.google
        if not google.owner:
            google._update(client_id='test.apps.googleusercontent.com', client_secret='secret', owner=OWNER, allowed=[OWNER])
        import secrets
        self.cred = secrets.token_urlsafe(32)
        self.app.state.sessions.create(self.cred, OWNER, 'browser', '')

        # Create widget token directly or via call
        transport = httpx.ASGITransport(app=self.app, client=('127.0.0.1', 50000))
        async with httpx.AsyncClient(transport=transport, base_url='http://127.0.0.1') as client:
            client.cookies.set('stackpad_session', self.cred)
            res = await client.post('/api/widget/tokens', json={'name': 'Pixel'}, headers={'Origin': 'http://127.0.0.1'})
            self.assertEqual(res.status_code, 200)
            self.token = res.json()['token']

    async def _open_stream(self, path: str, headers: dict = None):
        scope = {
            'type': 'http',
            'asgi': {'version': '3.0', 'spec_version': '2.4'},
            'http_version': '1.1',
            'method': 'GET',
            'scheme': 'http',
            'path': path.split('?')[0],
            'raw_path': path.encode(),
            'query_string': path.split('?')[1].encode() if '?' in path else b'',
            'headers': [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()],
            'client': ('127.0.0.1', 50000),
            'server': ('127.0.0.1', 80),
        }
        queue = asyncio.Queue()

        async def receive():
            return {'type': 'http.request', 'body': b'', 'more_body': False}

        async def send(msg):
            await queue.put(msg)

        task = asyncio.create_task(self.app(scope, receive, send))
        return queue, task

    async def test_unauthenticated_request_blocked(self):
        queue, task = await self._open_stream('/api/events')
        try:
            start_msg = await asyncio.wait_for(queue.get(), timeout=2.0)
            self.assertEqual(start_msg['type'], 'http.response.start')
            self.assertEqual(start_msg['status'], 401)
        finally:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    async def test_widget_token_topic_restriction(self):
        headers = {'Authorization': f'Bearer {self.token}'}

        # widget token requesting services -> 403
        q1, t1 = await self._open_stream('/api/events?topics=services', headers=headers)
        try:
            msg = await asyncio.wait_for(q1.get(), timeout=2.0)
            self.assertEqual(msg['status'], 403)
        finally:
            t1.cancel()
            try:
                await t1
            except asyncio.CancelledError:
                pass

        # widget token requesting alert,services -> 403
        q2, t2 = await self._open_stream('/api/events?topics=alert,services', headers=headers)
        try:
            msg = await asyncio.wait_for(q2.get(), timeout=2.0)
            self.assertEqual(msg['status'], 403)
        finally:
            t2.cancel()
            try:
                await t2
            except asyncio.CancelledError:
                pass

        # widget token requesting only alert -> 200 stream & alert event received
        q3, t3 = await self._open_stream('/api/events?topics=alert', headers=headers)
        try:
            start = await asyncio.wait_for(q3.get(), timeout=2.0)
            self.assertEqual(start['status'], 200)
            conn = await asyncio.wait_for(q3.get(), timeout=2.0)
            self.assertIn(b': connected', conn['body'])

            # Publish an alert
            self.app.state.engine.events.publish('alert', {'kind': 'process_crash', 'name': 'Demo'})
            alert_msg = await asyncio.wait_for(q3.get(), timeout=2.0)
            self.assertIn(b'event: alert', alert_msg['body'])
            self.assertIn(b'process_crash', alert_msg['body'])
        finally:
            t3.cancel()
            try:
                await t3
            except asyncio.CancelledError:
                pass

    async def test_authenticated_stream_sends_initial_payloads(self):
        headers = {'Cookie': f'stackpad_session={self.cred}'}
        queue, task = await self._open_stream('/api/events?topics=services,settings', headers=headers)
        try:
            start = await asyncio.wait_for(queue.get(), timeout=2.0)
            self.assertEqual(start['status'], 200)

            conn = await asyncio.wait_for(queue.get(), timeout=2.0)
            self.assertIn(b': connected', conn['body'])

            services_chunk = await asyncio.wait_for(queue.get(), timeout=2.0)
            self.assertIn(b'event: services', services_chunk['body'])

            settings_chunk = await asyncio.wait_for(queue.get(), timeout=2.0)
            self.assertIn(b'event: settings', settings_chunk['body'])
        finally:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    async def test_stream_answers_in_the_requested_language(self):
        headers = {'Cookie': f'stackpad_session={self.cred}', 'X-StackPad-Lang': 'en'}
        queue, task = await self._open_stream('/api/events?topics=alert', headers=headers)
        try:
            await asyncio.wait_for(queue.get(), timeout=2.0)
            await asyncio.wait_for(queue.get(), timeout=2.0)
            self.app.state.engine.events.publish('alert', {'kind': 'crashed', 'pad_name': '데모', 'message': '프로세스가 종료되었습니다. 로그를 확인해 주세요.\nError: boom'})
            alert = await asyncio.wait_for(queue.get(), timeout=2.0)
            data = json.loads(alert['body'].decode().split('data: ', 1)[1])
            self.assertEqual(data['message'], 'The process exited. Check the logs.\nError: boom')
            self.assertEqual(data['pad_name'], '데모')
        finally:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass


if __name__ == '__main__':
    unittest.main()

