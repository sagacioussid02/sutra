"""Starting, recording and capping research runs."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo

from .store import AgentStore
from .types import Budget, Findings
from .worker import ResearchWorker

log = logging.getLogger("sutra_orchestrator")

DAILY_RUNS_REPLY = "I've used today's research runs already. Ask me again tomorrow."
DAILY_TOKENS_REPLY = "I've used up today's research allowance. Ask me again tomorrow."


class AgentService:
    def __init__(
        self,
        store: AgentStore,
        worker: ResearchWorker,
        budget: Budget,
        tz: ZoneInfo,
        *,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._store = store
        self._worker = worker
        self._budget = budget
        self._tz = tz
        self._now = now or (lambda: datetime.now(timezone.utc))

    @property
    def store(self) -> AgentStore:
        return self._store

    @property
    def budget(self) -> Budget:
        return self._budget

    def today_usage(self) -> tuple[int, int]:
        local = self._now().astimezone(self._tz)
        start = datetime.combine(local.date(), time.min, tzinfo=self._tz)
        return self._store.usage_since(start)

    def refusal(self) -> str | None:
        """Why a new run cannot start today, or None if it can."""
        runs, tokens = self.today_usage()
        if runs >= self._budget.daily_runs:
            return DAILY_RUNS_REPLY
        if tokens >= self._budget.daily_tokens:
            return DAILY_TOKENS_REPLY
        return None

    async def run(self, task: str, *, budget: Budget | None = None, tag: str = "") -> Findings:
        """Run one research task and record it. Cancellation is recorded as interrupted.

        ``tag`` marks who asked (shown in the run record, never sent to the model); ``budget``
        can only narrow the run's limits.
        """
        run_id = self._store.start(f"{tag} {task}" if tag else task, self._now())
        try:
            findings = await self._worker.run(task, budget)
        except asyncio.CancelledError:
            self._store.interrupt(run_id, self._now())
            raise
        except Exception:
            log.warning("research run failed", exc_info=True)
            findings = Findings()
            self._store.finish(run_id, findings, self._now(), failed=True)
            raise
        self._store.finish(run_id, findings, self._now())
        return findings
