"""The reminder scheduler: a deterministic poll loop with no model in it.

The scheduler never calls a model and never decides anything: it reads
due reminders from the store, claims each one atomically, and puts it in
the inbox. Parsing happened once, when the reminder was created; firing
is pure code.

Missed-fire policy: if the process was down when a reminder came due,
the reminder is not dropped. On the first sweep after the scheduler
starts, every reminder that came due before the scheduler started is
fired exactly once and marked ``late`` in the inbox, so the user can
tell it arrived after the fact. Reminders that come due while the
scheduler is running are delivered on time (within one poll interval)
and are not marked late.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import datetime, timezone

from .store import InboxRow, ReminderStore

log = logging.getLogger("sutra_orchestrator")


class ReminderScheduler:
    def __init__(
        self,
        store: ReminderStore,
        *,
        poll_interval: float = 5.0,
        on_deliver: Callable[[InboxRow], None] | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._store = store
        self._poll_interval = poll_interval
        self._on_deliver = on_deliver
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._started_at: datetime | None = None
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        """Mark the scheduler's start; reminders due before this are late."""
        if self._started_at is None:
            self._started_at = self._now()

    def fire_due(self, now: datetime | None = None) -> list[InboxRow]:
        """One sweep: claim and deliver every reminder due by ``now``.

        One bad reminder never aborts the sweep: a store error while
        claiming or delivering it is logged and the sweep moves on to
        the next due reminder. If the error struck after the claim was
        won, the reminder stays ``fired`` and is not retried — the fire
        is on record, and retrying would risk delivering it twice. Only
        the inbox entry is lost, and the failure is in the log.
        """
        now = now or self._now()
        if self._started_at is None:
            self._started_at = now
        delivered: list[InboxRow] = []
        for row in self._store.due(now):
            late = row.fire_at < self._started_at
            try:
                if not self._store.claim(row.id, now, late=late):
                    continue  # another loop won the claim; it owns delivery
                claimed = self._store.get(row.id)
                assert claimed is not None
                entry = self._store.deliver(claimed, now)
            except Exception:
                log.warning("reminder %s failed to fire", row.id, exc_info=True)
                continue
            delivered.append(entry)
            if self._on_deliver is not None:
                try:
                    self._on_deliver(entry)
                except Exception:
                    log.warning("reminder delivery callback failed", exc_info=True)
        return delivered

    async def run(self) -> None:
        self.start()
        while True:
            try:
                self.fire_due()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                # Same guard as the other background loops: one bad tick
                # (a transient store error, say) must not kill the loop
                # and silently stop every future reminder with it.
                log.warning("reminder sweep failed (%s); will retry", type(exc).__name__)
            await asyncio.sleep(self._poll_interval)

    def start_task(self) -> asyncio.Task[None]:
        if self._task is None:
            self._task = asyncio.create_task(self.run(), name="sutra-reminders")
        return self._task

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
