"""The event service: intake from the gateway, at-least-once drain to consumers, expiry."""

from __future__ import annotations

import asyncio
import inspect
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from .kinds import Event, EventError, parse_envelope
from .store import EventStore

log = logging.getLogger(__name__)

Handler = Callable[[Event], Awaitable[None] | None]
DRAIN_BATCH = 50


def untrusted_block(event: Event) -> str:
    """The only way event text reaches a prompt: labelled data from an outside program, never instructions."""
    body = " ".join(f"{k}: {v}" for k, v in sorted(event.payload.items())).replace("</untrusted_event>", "")
    return f'<untrusted_event source="{event.source}" kind="{event.kind}">{body}</untrusted_event>'


@dataclass
class Consumer:
    name: str
    kinds: tuple[str, ...]
    handler: Handler


class EventsService:
    def __init__(
        self,
        store: EventStore,
        *,
        secret: str,
        enabled: bool = True,
        cap: int = 5000,
        retention_days: int = 30,
        max_attempts: int = 3,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.store = store
        self.secret = secret
        self.enabled = enabled
        self._cap = cap
        self._retention = timedelta(days=retention_days)
        self._max_attempts = max(1, max_attempts)
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._consumers: dict[str, Consumer] = {}
        self._task: asyncio.Task[None] | None = None

    # ------------------------------------------------------------------ intake

    def ingest(self, data: object) -> bool:
        """Validate and store a forwarded envelope. False for a duplicate; EventError if refused."""
        if not self.enabled:
            raise EventError("events are off")
        event = parse_envelope(data, self._now())
        if self.store.count() >= self._cap:
            self.sweep()
            if self.store.count() >= self._cap:
                raise EventError("the event log is full")
        return self.store.append(event)

    # ----------------------------------------------------------------- consumers

    def register(self, name: str, kinds: tuple[str, ...], handler: Handler) -> None:
        self._consumers[name] = Consumer(name, kinds, handler)

    async def drain(self) -> int:
        """Offer each consumer its new events. Returns how many were handled."""
        if not self.enabled:
            return 0
        handled = 0
        for c in self._consumers.values():
            for event in self.store.drain(c.name, c.kinds, self._now(), DRAIN_BATCH):
                try:
                    if not self.store.was_handled(c.name, event.id):
                        result = c.handler(event)
                        if inspect.isawaitable(result):
                            await result
                        self.store.mark_handled(c.name, event.id)
                        handled += 1
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    failures = self.store.record_failure(c.name, event.seq, type(exc).__name__)
                    if failures < self._max_attempts:
                        break  # keep order: this event is offered again on the next drain
                    log.warning("event %s skipped for %s after %d failures", event.id, c.name, failures)
                    self.store.record_skip(c.name, event.seq, type(exc).__name__, self._now())
                self.store.advance(c.name, event.seq)
        return handled

    def sweep(self) -> int:
        now = self._now()
        return self.store.sweep(now, now - self._retention)

    # ---------------------------------------------------------------- background

    def start_task(self, interval: float = 15.0) -> asyncio.Task[None]:
        async def loop() -> None:
            ticks = 0
            while True:
                try:
                    await self.drain()
                    ticks += 1
                    if ticks % 20 == 0:
                        self.sweep()
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    log.warning("event drain failed (%s); will retry", type(exc).__name__)
                await asyncio.sleep(interval)

        if self._task is None:
            self._task = asyncio.create_task(loop(), name="sutra-events")
        return self._task

    async def stop_task(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
