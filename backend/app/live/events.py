"""Bounded fan-out queues that isolate serial ingestion from WebSocket clients."""

from __future__ import annotations

from queue import Empty, Full, Queue
from threading import Lock
from typing import Any


class LiveEventBroker:
    """Publish JSON-ready events without allowing slow consumers to block producers."""

    def __init__(self, queue_size: int = 16) -> None:
        if queue_size < 1:
            raise ValueError("Live event queue size must be at least one.")
        self._queue_size = queue_size
        self._subscriptions: set[Queue[dict[str, Any]]] = set()
        self._lock = Lock()

    def subscribe(self) -> Queue[dict[str, Any]]:
        """Create one bounded queue for an individual WebSocket client."""

        subscription: Queue[dict[str, Any]] = Queue(maxsize=self._queue_size)
        with self._lock:
            self._subscriptions.add(subscription)
        return subscription

    def unsubscribe(self, subscription: Queue[dict[str, Any]]) -> None:
        """Discard the queue for a closed WebSocket client."""

        with self._lock:
            self._subscriptions.discard(subscription)

    def publish(self, event: dict[str, Any]) -> None:
        """Fan out an event, replacing stale queued snapshots for slow clients."""

        with self._lock:
            subscriptions = tuple(self._subscriptions)

        for subscription in subscriptions:
            try:
                subscription.put_nowait(event)
            except Full:
                try:
                    subscription.get_nowait()
                except Empty:
                    continue
                try:
                    subscription.put_nowait(event)
                except Full:
                    # A concurrent consumer refilled the bounded queue. The next event wins.
                    continue

    def subscription_count(self) -> int:
        """Return active client queues for diagnostics and tests."""

        with self._lock:
            return len(self._subscriptions)