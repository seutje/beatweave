import asyncio
import threading
from collections.abc import AsyncIterator
from typing import Any

from beatweave.schemas import EventMessage


class EventBroker:
    """Fan out backend events to all currently connected websocket clients."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._subscribers: set[asyncio.Queue[EventMessage]] = set()
        self._loop: asyncio.AbstractEventLoop | None = None

    def bind(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def publish(self, event_type: str, payload: dict[str, Any]) -> None:
        event = EventMessage(type=event_type, payload=payload)
        loop = self._loop
        if loop is None or loop.is_closed():
            return
        loop.call_soon_threadsafe(self._deliver, event)

    def _deliver(self, event: EventMessage) -> None:
        with self._lock:
            subscribers = tuple(self._subscribers)
        for queue in subscribers:
            queue.put_nowait(event)

    async def subscribe(self) -> AsyncIterator[EventMessage]:
        queue: asyncio.Queue[EventMessage] = asyncio.Queue()
        with self._lock:
            self._subscribers.add(queue)
        try:
            while True:
                yield await queue.get()
        finally:
            with self._lock:
                self._subscribers.discard(queue)
