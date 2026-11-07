"""Memory distillation: a scheduled, capped, resumable pass that turns recent episodes into proposals.

The pass reads episode records only (what the person said, which tools ran and how they ended,
confirmation outcomes), never tool payloads or replies. Whatever it finds is stored as a proposal for
the user to review; nothing is recalled or treated as fact until they approve it.
"""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from ..classifier import AFFIRMATIVES, NEGATIVES
from ..memstore import SqliteMemory
from ..memstore.textutil import normalize
from ..model import StructuredModel
from ..prompts import load_prompt

log = logging.getLogger("sutra_orchestrator")

BATCH = 60
UTTERANCE_CHARS = 240
STATEMENT_CHARS = 160
HORIZON_CHARS = 60
MAX_NEW_PER_PASS = 5
MAX_PENDING = 25
QUIET_MINUTES = 30
KINDS = ("fact", "preference", "commitment")
_TRIVIAL = AFFIRMATIVES | NEGATIVES
_AMOUNT = re.compile(r"[$€£]\s*\d|\b\d[\d,]*(?:\.\d+)?\s*(?:dollars|usd|bucks|k)\b|\b(?:balance|account number|password|ssn)\b", re.I)


@dataclass
class PassResult:
    read: int = 0
    sent: int = 0
    created: int = 0
    commitments: int = 0
    skipped: str = ""
    ids: list[int] = field(default_factory=list)


class DistillService:
    def __init__(
        self,
        memory: SqliteMemory,
        model: StructuredModel,
        *,
        enabled: bool = True,
        hours: float = 24.0,
        daily_calls: int = 3,
        batch: int = BATCH,
        exclude_tool_prefixes: tuple[str, ...] = ("finanxe_",),
        last_activity: Callable[[], datetime] | None = None,
        busy: Callable[[], bool] | None = None,
        digest: Callable[[PassResult], None] | None = None,
        timeout: float = 60.0,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._memory = memory
        self._model = model
        self.enabled = enabled
        self._hours = hours
        self._daily_calls = daily_calls
        self._batch = batch
        self._exclude = exclude_tool_prefixes
        self._last_activity = last_activity
        self._busy = busy
        self._digest = digest
        self._timeout = timeout
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._task: asyncio.Task[None] | None = None
        self._lock = asyncio.Lock()

    # -------------------------------------------------------------- bookkeeping

    def _mark(self) -> tuple[str, str] | None:
        ts, eid = self._memory.get_meta("watermark_ts"), self._memory.get_meta("watermark_id")
        return (ts, eid or "") if ts else None

    def _set_mark(self, ts: str, eid: str) -> None:
        self._memory.set_meta("watermark_ts", ts)
        self._memory.set_meta("watermark_id", eid)

    def status(self) -> list[str]:
        m, now = self._memory, self._now()
        mark = self._mark()
        last = m.get_meta("last_run")
        lines = [f"Distillation is {'on' if self.enabled else 'off'}."]
        lines.append("  Last pass: " + (f"{_ago(datetime.fromisoformat(last), now)}, {m.get_meta('last_outcome') or 'no outcome'}" if last else "never"))
        lines.append("  Position: " + (f"episodes up to {mark[0][:16]}" if mark else "not started (the first pass starts from now)"))
        lines.append(f"  Model calls today: {self._calls_today()} of {self._daily_calls}")
        waiting = sum(1 for p in m.proposals() if p.distilled)
        lines.append(f"  Distilled proposals waiting: {waiting} (see /proposals)")
        return lines

    def _calls_key(self) -> str:
        return f"calls:{self._now():%Y-%m-%d}"

    def _calls_today(self) -> int:
        return int(self._memory.get_meta(self._calls_key()) or 0)

    def due(self) -> bool:
        last = self._memory.get_meta("last_run")
        return last is None or self._now() - datetime.fromisoformat(last) >= timedelta(hours=self._hours)

    # ------------------------------------------------------------------- the pass

    async def run_pass(self, *, backfill: bool = False) -> PassResult:
        """One pass. The watermark moves only over episodes that were actually examined."""
        async with self._lock:
            return await self._run(backfill)

    async def _run(self, backfill: bool) -> PassResult:
        m, now = self._memory, self._now()
        if not self.enabled:
            return PassResult(skipped="distillation is off")
        mark = self._mark()
        if mark is None:
            if backfill:
                mark = ("", "")  # opt-in: start from the beginning of the hot episodes
            else:
                latest = m.latest_episode_mark()
                if latest is not None:
                    self._set_mark(*latest)  # enabling it must not flood the user with old conversations
                m.set_meta("last_run", now.isoformat())
                m.set_meta("last_outcome", "started from now; nothing to read yet")
                return PassResult(skipped="started from now")
        rows = m.episodes_after(mark, self._batch)
        if not rows:
            m.set_meta("last_run", now.isoformat())
            m.set_meta("last_outcome", "no new conversations")
            return PassResult(skipped="no new conversations")
        if sum(1 for p in m.proposals() if p.distilled) >= MAX_PENDING:
            return PassResult(read=len(rows), skipped="too many proposals are waiting for review")
        if self._calls_today() >= self._daily_calls:
            return PassResult(read=len(rows), skipped="today's model-call cap is reached; the rest waits")

        shown = [r for r in rows if self._usable(r)]
        result = PassResult(read=len(rows), sent=len(shown))
        if shown:
            m.set_meta(self._calls_key(), str(self._calls_today() + 1))
            try:
                raw = await asyncio.wait_for(
                    self._model.structured(name="distill_candidates", system=load_prompt("distill.md"), user=self._message(shown)),
                    timeout=self._timeout,
                )
            except Exception as exc:  # nothing is created and the watermark does not move: next pass retries
                log.warning("distillation failed (%s); will retry", type(exc).__name__)
                m.set_meta("last_outcome", f"failed ({type(exc).__name__}); will retry")
                result.skipped = "the model call failed"
                return result
            self._apply(raw, shown, result)
        last = rows[-1]
        self._set_mark(last[1], last[0])
        m.set_meta("last_run", now.isoformat())
        m.set_meta("last_outcome", f"{result.created} proposed from {result.read} conversations")
        if result.created and self._digest is not None:
            self._digest(result)
        return result

    def _usable(self, row: tuple[str, str, str, list[dict[str, str]], str | None]) -> bool:
        _, _, utterance, tools, _ = row
        names = [t.get("name", "") for t in tools]
        if any(n.startswith(p) for n in names for p in self._exclude if p):
            return False  # finance conversations are never read
        text = " ".join(utterance.split())
        return len(text.split()) >= 3 and normalize(text) not in _TRIVIAL

    def _message(self, shown: list[tuple[str, str, str, list[dict[str, str]], str | None]]) -> str:
        active = self._memory.active_for_distill()
        lines = ["Already remembered:"]
        lines += [f"[{r.id}] ({r.kind}) {r.content}" for r in active] or ["(nothing)"]
        rejected = self._memory.rejected_contents()
        lines += ["", "Declined before (do not record these or anything equivalent):"]
        lines += [f"- {c}" for c in rejected] or ["(none)"]
        lines += ["", "Entries:"]
        for i, (_, ts, utterance, tools, confirmation) in enumerate(shown, 1):
            extra = ""
            if tools:
                extra += " [tools: " + ", ".join(f"{t.get('name', '?')} ({t.get('status', '?')})" for t in tools) + "]"
            if confirmation:
                extra += f" [confirmation: {confirmation}]"
            lines.append(f"[{i}] ({ts[:10]}) Person: {' '.join(utterance.split())[:UTTERANCE_CHARS]}{extra}")
        return "\n".join(lines)

    def _apply(self, raw: Any, shown: list, result: PassResult) -> None:
        items = raw.get("items") if isinstance(raw, dict) else raw
        if not isinstance(items, list):
            return
        active = {r.id for r in self._memory.active_for_distill()}
        for item in items[:MAX_NEW_PER_PASS]:
            if not isinstance(item, dict):
                continue
            statement = " ".join(str(item.get("statement") or "").split())
            kind = item.get("kind")
            if not statement or len(statement) > STATEMENT_CHARS or kind not in KINDS or _AMOUNT.search(statement):
                continue
            # Provenance is only what was really shown: an invented number never becomes a link.
            picked = sorted({n for n in item.get("evidence") or [] if isinstance(n, int) and not isinstance(n, bool) and 1 <= n <= len(shown)})
            if not picked:
                continue
            supporting = [shown[n - 1] for n in picked]
            horizon = None
            if kind == "commitment":
                horizon = self._stated_horizon(item.get("horizon"), supporting)
            n = item.get("replaces")
            replaces = n if isinstance(n, int) and not isinstance(n, bool) and n in active else None
            new_id = self._memory.add_distilled(
                statement, kind, [r[0] for r in supporting], horizon=horizon, replaces=replaces
            )
            if new_id is not None:
                result.created += 1
                result.commitments += kind == "commitment"
                result.ids.append(new_id)

    @staticmethod
    def _stated_horizon(value: Any, supporting: list) -> str | None:
        """A horizon survives only if the person's own words contain it. A date is never invented."""
        text = " ".join(str(value or "").split())[:HORIZON_CHARS]
        if not text:
            return None
        said = " ".join(r[2] for r in supporting).lower()
        return text if text.lower() in said else None

    # ----------------------------------------------------------------- background

    async def maintain(self) -> None:
        if not self.enabled or not self.due():
            return
        now = self._now()
        if self._last_activity is not None and now - self._last_activity() < timedelta(minutes=QUIET_MINUTES):
            return
        if self._busy is not None and self._busy():
            return
        await self.run_pass()

    def start_task(self, interval: float = 1800.0) -> asyncio.Task[None]:
        async def loop() -> None:
            while True:
                try:
                    await self.maintain()
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    log.warning("distillation maintenance failed (%s); will retry", type(exc).__name__)
                await asyncio.sleep(interval)

        if self._task is None:
            self._task = asyncio.create_task(loop(), name="sutra-distill")
        return self._task

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None


def _ago(then: datetime, now: datetime) -> str:
    hours = int((now - then).total_seconds() // 3600)
    return "just now" if hours < 1 else (f"{hours} h ago" if hours < 48 else f"{hours // 24} days ago")
