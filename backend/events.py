"""Thread-safe event hub for StackPad real-time event distribution."""
import asyncio
import logging
import threading
from typing import Any, AsyncGenerator

logger = logging.getLogger(__name__)


class Subscriber:
    def __init__(self, queue: asyncio.Queue, loop: asyncio.AbstractEventLoop, topics: set[str] | None):
        self.queue = queue
        self.loop = loop
        self.topics = topics


class EventHub:
    def __init__(self):
        self.lock = threading.Lock()
        self._subscribers: set[Subscriber] = set()

    @property
    def subscribers(self) -> int:
        with self.lock:
            return len(self._subscribers)

    def register(self, topics: set[str] | list[str] | None = None):
        loop = asyncio.get_running_loop()
        queue = asyncio.Queue(maxsize=64)
        sub = Subscriber(queue=queue, loop=loop, topics=set(topics) if topics else None)
        with self.lock:
            self._subscribers.add(sub)

        def unsub():
            with self.lock:
                self._subscribers.discard(sub)

        return queue, unsub

    def publish(self, topic: str, data: Any):
        with self.lock:
            subs = list(self._subscribers)
        for sub in subs:
            if sub.topics is not None and topic not in sub.topics:
                continue
            try:
                if not sub.loop.is_closed():
                    sub.loop.call_soon_threadsafe(self._enqueue, sub.queue, topic, data)
            except RuntimeError:
                pass

    @staticmethod
    def _enqueue(queue: asyncio.Queue, topic: str, data: Any):
        item = (topic, data)
        if topic == 'services':
            items = []
            while not queue.empty():
                try:
                    existing = queue.get_nowait()
                    if existing[0] != 'services':
                        items.append(existing)
                except asyncio.QueueEmpty:
                    break
            for it in items:
                try:
                    queue.put_nowait(it)
                except asyncio.QueueFull:
                    break
        if queue.full():
            try:
                queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
        try:
            queue.put_nowait(item)
        except asyncio.QueueFull:
            pass

    async def subscribe(self, topics: set[str] | list[str] | None = None) -> AsyncGenerator[tuple[str, Any], None]:
        queue, unsub = self.register(topics)
        try:
            while True:
                item = await queue.get()
                yield item
        finally:
            unsub()
