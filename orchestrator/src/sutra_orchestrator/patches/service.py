"""Starting, finishing, capping and discarding patch runs.

A run drafts in a fresh worktree, then the finished diff is checked against the protected list.
A draft that touches a protected path, or changes nothing, is removed. Nothing here merges,
pushes, installs or applies a draft.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import datetime, time, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from ..agents.types import Budget
from .drafter import Draft, Drafter
from .store import PatchRow, PatchStore
from .workspace import Workspace

log = logging.getLogger("sutra_orchestrator")

DAILY_RUNS_REPLY = "I've used today's drafting runs already. Ask me again tomorrow."
DAILY_TOKENS_REPLY = "I've used up today's drafting allowance. Ask me again tomorrow."
MAX_SUMMARY = 2000


class PatchResult:
    """What a finished run is: a row id, its status, and the drafter's untrusted summary."""

    def __init__(self, row: PatchRow) -> None:
        self.row = row


class PatchService:
    def __init__(
        self,
        store: PatchStore,
        drafter: Drafter,
        repo: Path,
        base_dir: Path,
        budget: Budget,
        tz: ZoneInfo,
        *,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._store = store
        self._drafter = drafter
        self._repo = repo
        self._base_dir = base_dir
        self._budget = budget
        self._tz = tz
        self._now = now or (lambda: datetime.now(timezone.utc))

    @property
    def store(self) -> PatchStore:
        return self._store

    @property
    def budget(self) -> Budget:
        return self._budget

    def today_usage(self) -> tuple[int, int]:
        local = self._now().astimezone(self._tz)
        return self._store.usage_since(datetime.combine(local.date(), time.min, tzinfo=self._tz))

    def refusal(self) -> str | None:
        runs, tokens = self.today_usage()
        if runs >= self._budget.daily_runs:
            return DAILY_RUNS_REPLY
        if tokens >= self._budget.daily_tokens:
            return DAILY_TOKENS_REPLY
        return None

    async def run(self, task: str) -> PatchResult:
        """Draft ``task`` on a new branch. Cancellation is recorded as interrupted and cleaned up."""
        pid = self._store.start(task, self._now())
        ws: Workspace | None = None
        try:
            ws = await asyncio.to_thread(Workspace.create, self._repo, self._base_dir, str(pid))
            self._store.set_branch(pid, ws.branch)
            draft = await self._drafter.run(task, ws)
            await self._finish(pid, ws, draft)
        except asyncio.CancelledError:
            self._store.interrupt(pid, self._now())
            if ws is not None:
                await asyncio.to_thread(ws.remove)
            raise
        except Exception:
            log.warning("patch run failed", exc_info=True)
            self._store.finish(pid, "failed", self._now(), reason="error")
            if ws is not None:
                await asyncio.to_thread(ws.remove)
            raise
        row = self._store.get(pid)
        assert row is not None
        return PatchResult(row)

    async def _finish(self, pid: int, ws: Workspace, draft: Draft) -> None:
        common = dict(
            tool_calls=draft.tool_calls, output_tokens=draft.output_tokens,
            refusals=ws.refusals, summary=draft.summary[:MAX_SUMMARY],
        )
        entries = await asyncio.to_thread(ws.stage_and_diff)
        bad = ws.violations(entries)
        if bad:
            log.warning("patch %s rejected: touches %s", pid, bad)
            await asyncio.to_thread(ws.remove)
            self._store.finish(
                pid, "rejected", self._now(), reason="protected: " + ", ".join(bad[:5]),
                files=[], test_status="untested", **common,
            )
            return
        if not entries:
            await asyncio.to_thread(ws.remove)
            self._store.finish(pid, "failed", self._now(), reason="no changes", **common)
            return
        files = sorted({e.path for e in entries})
        test = draft.test
        await asyncio.to_thread(ws.commit, f"Draft #{pid}: {_one_line(draft.summary)}")
        stat = await asyncio.to_thread(ws.diff_stat)
        self._store.finish(
            pid, "partial" if draft.partial else "drafted", self._now(), reason=draft.reason,
            files=files, test_status=test.status, test_detail=test.detail, diff_stat=stat, **common,
        )

    # ------------------------------------------------------------ discarding

    def discard(self, pid: int) -> bool:
        row = self._store.get(pid)
        if row is None or row.status == "discarded":
            return False
        Workspace.attach(self._repo, self._base_dir, str(pid)).remove()
        self._store.mark_discarded(pid)
        return True

    def discard_all(self) -> int:
        count = 0
        for row in self._store.list_patches(10_000):
            if self.discard(row.id):
                count += 1
        return count


def _one_line(text: str) -> str:
    return " ".join(text.split())[:72] or "untitled"
