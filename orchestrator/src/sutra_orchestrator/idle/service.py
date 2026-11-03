"""Idle research: when the user is away, look into something they care about, within tight rails.

The picker chooses, code checks, the existing sandboxed research run does the looking, and
the result goes to the offers system as an expiring signal that is judged and asked about.
Nothing here speaks to the user, writes memory or acts on what it finds.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from ..agents import AgentService
from ..agents.types import Budget
from ..graph import GraphService
from ..interests import InterestService
from ..interests.reflect import similar
from ..model import ModelClient, StructuredModel
from ..offers import OffersService
from .picker import PLAN_DAYS, Picker, Topic, brief_problem, reactions
from .store import IdleStore
from .summarize import summarize

log = logging.getLogger("sutra_orchestrator")

QUIET_MINUTES = 30  # matches the graph's idle gap: the conversation is over
CHECK_SECONDS = 600
FINDING_LIFETIME = timedelta(days=3)
SKIP_AFTER_BAD_BRIEF = timedelta(days=1)
MAX_GAP_DOUBLINGS = 3
USER_RESERVE_TOKEN_SHARE = 1 / 3  # the user's own research keeps at least this much of the day
SOURCE = "idle-research"
PLAN_MODES = ("planned", "decided")


class _Model(StructuredModel, ModelClient):  # both protocols, one real object
    pass


class IdleResearcher:
    def __init__(
        self,
        store: IdleStore,
        *,
        interests: InterestService | None,
        graph: GraphService | None,
        agents: AgentService | None,
        offers: OffersService | None,
        model: _Model,
        tz: ZoneInfo,
        last_activity: Callable[[], datetime],
        busy: Callable[[], bool],
        budget: Budget,
        daily_runs: int = 1,
        min_hours: float = 48.0,
        default_enabled: bool = False,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._store = store
        self._interests = interests
        self._graph = graph
        self._agents = agents
        self._offers = offers
        self._model = model
        self._tz = tz
        self._last_activity = last_activity
        self._busy = busy
        self._budget = budget
        self._daily_runs = daily_runs
        self._min_hours = min_hours
        self._default_enabled = default_enabled
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._picker = Picker(model, spend=offers.spend_call if offers else None)
        self._lock = asyncio.Lock()
        self._task: asyncio.Task[None] | None = None

    @property
    def store(self) -> IdleStore:
        return self._store

    # ----------------------------------------------------------------- switch

    @property
    def enabled(self) -> bool:
        stored = self._store.get_meta("enabled")
        return self._default_enabled if stored is None else stored == "1"

    def set_enabled(self, on: bool) -> None:
        self._store.set_meta("enabled", "1" if on else "0")

    # ------------------------------------------------------------ eligibility

    def blocker(self, *, force: bool = False) -> str | None:
        """Why a run may not start now, or None. ``force`` waives only the quiet-time test."""
        now = self._now()
        if not self.enabled:
            return "idle research is off"
        if self._interests is None or self._agents is None or self._offers is None:
            return "it needs interests, research agents and offers"
        if not self._offers.enabled:
            return "offers are off"
        if not force and now - self._last_activity() < timedelta(minutes=QUIET_MINUTES):
            return "you were here a moment ago"
        if self._busy():
            return "something is running or waiting for your answer"
        local = now.astimezone(self._tz)
        midnight = datetime.combine(local.date(), time.min, tzinfo=self._tz)
        if self._store.ran_since(midnight) >= self._daily_runs:
            return "today's idle run has been used"
        last = self._store.last_ran()
        streak = int(self._store.get_meta("streak") or 0)
        gap = timedelta(hours=self._min_hours * 2 ** min(streak, MAX_GAP_DOUBLINGS))
        if last is not None and now - last < gap:
            return f"too soon after the last run (next after {(last + gap).astimezone(self._tz):%b %d %H:%M})"
        refusal = self._agents.refusal()
        if refusal is not None:
            return "the research allowance for today is used"
        runs, tokens = self._agents.today_usage()
        b = self._agents.budget
        if runs + 1 > b.daily_runs - 1 or tokens > b.daily_tokens * (1 - USER_RESERVE_TOKEN_SHARE):
            return "keeping the rest of today's research for your own requests"
        return None

    # ----------------------------------------------------------------- topics

    def _blocked(self, label: str) -> bool:
        assert self._offers is not None
        return self._offers.arbiter.is_blocked("timely", label)

    def topics(self) -> list[Topic]:
        assert self._interests is not None and self._offers is not None
        now = self._now()
        runs = self._store.recent(50)
        outcomes = self._offers.store.topic_outcomes(now - timedelta(days=90))

        def waiting(label: str) -> bool:
            return any(
                r.not_before and r.not_before > now and (similar(label, r.topic) or similar(r.topic, label))
                for r in runs
            )

        out: list[Topic] = []
        for row in self._interests.store.list(("active",)):
            if self._blocked(row.topic) or waiting(row.topic):
                continue
            last = next((r for r in runs if similar(row.topic, r.topic) and r.outcome in ("done", "partial")), None)
            seen = "never researched" if last is None else f"researched {(now - last.created_at).days} day(s) ago"
            out.append(Topic(row.topic, "interest", f"{seen}; reactions: {reactions(row.topic, outcomes)}"))
        if self._graph is not None:
            for node in self._graph.store.list():
                age = (now - node.last_touched).days
                if node.mode not in PLAN_MODES or age > PLAN_DAYS:
                    continue
                if self._blocked(node.topic) or waiting(node.topic) or any(similar(node.topic, t.label) for t in out):
                    continue
                out.append(Topic(node.topic, "plan", f"a recent plan, {age} day(s) ago; reactions: {reactions(node.topic, outcomes)}"))
        return out

    # -------------------------------------------------------------------- run

    async def maybe_run(self, *, force: bool = False) -> str:
        """Try one run. Returns why nothing happened, or a one-line account of what did."""
        async with self._lock:
            why = self.blocker(force=force)
            if why:
                return why
            return await self._run_once()

    async def _run_once(self) -> str:
        assert self._agents is not None and self._offers is not None
        now = self._now()
        topics = self.topics()
        if not topics:
            return "nothing to research: no approved interests or recent plans"
        runs = self._store.recent(10)
        earlier = [f"{r.topic} ({r.created_at:%Y-%m-%d}, {r.outcome})" for r in runs if r.outcome != "skipped"]
        today = now.astimezone(self._tz)
        pick = await self._picker.pick(topics, now, earlier, f"{today:%A, %B} {today.day}, {today.year}")
        if pick is None:
            return "nothing worth researching right now"
        bar = self._offers.bars.value("research", now)
        if pick.value < bar:
            return f"not worth it yet: {pick.topic.label} (value {pick.value:.2f}, bar {bar:.2f})"
        blocked_words = [b.topic for b in self._offers.store.blocks() if b.topic]
        problem = brief_problem(pick.brief, blocked_words)
        if problem:
            self._store.add_run(
                pick.topic.label, f"(brief rejected: {problem})", pick.kind, "skipped", now,
                not_before=now + SKIP_AFTER_BAD_BRIEF,
            )
            return f"dropped a brief for {pick.topic.label}: it was not safe to send ({problem})"

        run_id = self._store.add_run(
            pick.topic.label, pick.brief, pick.kind, "running", now,
            not_before=now + timedelta(days=pick.revisit_days),
        )
        try:
            findings = await self._agents.run(pick.brief, budget=self._budget, tag="[idle]")
        except asyncio.CancelledError:
            self._store.finish(run_id, "interrupted")
            raise
        except Exception:
            self._store.finish(run_id, "failed")
            self._bump_streak(failed=True)
            return f"the run on {pick.topic.label} failed"
        summary = ""
        if findings.text:
            try:
                summary = await summarize(self._model, pick.brief, findings, now.astimezone(self._tz))
            except asyncio.CancelledError:
                self._store.finish(run_id, "interrupted", findings=findings.text)
                raise
            except Exception:
                log.warning("idle summary failed", exc_info=True)
        if not summary:
            self._store.finish(run_id, "empty", findings=findings.text)
            self._bump_streak(failed=True)
            return f"the run on {pick.topic.label} found nothing useful"
        signal_id = self._offers.add_signal(
            "research", summary, source=SOURCE, urgency="low",
            expires_at=now + FINDING_LIFETIME, topic_hint=pick.topic.label,
        )
        self._store.finish(
            run_id, "partial" if findings.partial else "done",
            findings=findings.text, summary=summary, signal_id=signal_id,
        )
        self._bump_streak(failed=False)
        return f"researched {pick.topic.label}; the finding is waiting to be offered"

    def _bump_streak(self, *, failed: bool) -> None:
        streak = int(self._store.get_meta("streak") or 0)
        self._store.set_meta("streak", str(min(streak + 1, MAX_GAP_DOUBLINGS) if failed else 0))

    # ------------------------------------------------------------- background

    def start_task(self, interval: float = CHECK_SECONDS) -> asyncio.Task[None]:
        async def loop() -> None:
            while True:
                try:
                    await self.maybe_run()
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    log.warning("idle research check failed (%s); will retry", type(exc).__name__)
                await asyncio.sleep(interval)

        if self._task is None:
            self._task = asyncio.create_task(loop(), name="sutra-idle-research")
        return self._task

    async def stop_task(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
