"""Offers as the rest of Sutra sees it.

Two kinds, one arbiter. *Follow-ups* come from the episode graph: a subagent advises,
the judge decides, and the orchestrator appends the words to the reply. *Timely*
offers come from signals (a weather warning, a finished research run) that any
producer may write; a background pass judges them and the ready ones are said at the
next opening. Nothing here acts for the user: offers are speech only.
"""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from ..graph import Advice, Candidate, GraphService
from ..interests.reflect import similar
from ..memory import LocalTool, ToolContext
from .arbiter import DEFAULT_DAILY_MAX, Arbiter
from .bars import UNCONNECTED_EXTRA, Bars
from .judge import Judge, Judgement
from .store import OffersStore, Signal

log = logging.getLogger("sutra_orchestrator")

STOP_TOOL = "stop_offers"
STATS_DAYS = 90
DROP_HOLD_DAYS = 30
URGENT_MAX_MINUTES = 60  # an urgent signal must be about to matter
DEFAULT_CALLS_PER_DAY = 200  # a rail on this feature's own model calls
KINDS = ("followup", "timely", "nudge")
URGENCIES = ("low", "medium", "high")
SIGNAL_SUMMARY_CHARS = 400
_DEFER = re.compile(
    r"\b(not now|not right now|later|maybe later|maybe tomorrow|another time|some other time|not today)\b",
    re.IGNORECASE,
)


RESEARCH_SOURCE = "idle-research"


def research_teaser(topic: str) -> str:
    """What is said about a research finding: its topic and nothing else, written in code."""
    return f"Something interesting turned up about {' '.join(topic.split())[:50]}, want to hear it?"


def is_deferral(text: str) -> bool:
    return bool(_DEFER.search(text))


@dataclass(frozen=True)
class OpenOffer:
    """An offer just put to the user, waiting for the answer on the next turn only."""

    offer_id: int
    kind: str  # "followup" or "timely"
    style: str  # "ask" or "tell"
    topic: str
    teaser: str
    step: str = "none"
    node_id: int | None = None
    signal_id: int | None = None
    source: str = ""  # who produced the signal, for a timely offer
    detail: str = ""  # a signal's summary: untrusted data, used only to deliver an accepted ask
    retry_hours: float = 6.0

    @property
    def description(self) -> str:
        if self.style == "tell":
            return f"The assistant told the user, unprompted: {self.teaser}"
        return f"The assistant offered, unprompted: {self.teaser}"


class OffersService:
    def __init__(
        self,
        store: OffersStore,
        tz: ZoneInfo,
        *,
        graph: GraphService | None = None,
        judge: Judge | None = None,
        daily_max: int = DEFAULT_DAILY_MAX,
        calls_per_day: int = DEFAULT_CALLS_PER_DAY,
        urgent_sources: tuple[str, ...] = (),
        now: Callable[[], datetime] | None = None,
        on_ready: Callable[[], None] | None = None,
    ) -> None:
        self._hooks: dict[str, Callable[[Signal, str], None]] = {}
        self._on_ready = on_ready
        self._store = store
        self._tz = tz
        self._graph = graph
        self._judge = judge
        self._arbiter = Arbiter(store, tz, daily_max=daily_max)
        self._bars = Bars(store)
        self._calls_per_day = calls_per_day
        self._urgent_sources = frozenset(urgent_sources)
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._task: asyncio.Task[None] | None = None
        self._lock = asyncio.Lock()

    def attach(self, graph: GraphService | None, judge: Judge | None) -> None:
        """Late wiring: the graph and the judge both spend this service's call budget."""
        self._graph = graph
        self._judge = judge

    @property
    def store(self) -> OffersStore:
        return self._store

    @property
    def arbiter(self) -> Arbiter:
        return self._arbiter

    @property
    def bars(self) -> Bars:
        return self._bars

    @property
    def enabled(self) -> bool:
        return self._arbiter.enabled()

    # ------------------------------------------------------------------ budget

    def spend_call(self) -> bool:
        """Count one model call against today's rail. False means the rail is reached."""
        key = f"calls:{self._now().astimezone(self._tz):%Y-%m-%d}"
        used = int(self._store.get_meta(key) or 0)
        if used >= self._calls_per_day:
            return False
        self._store.set_meta(key, str(used + 1))
        return True

    # ----------------------------------------------------------------- helpers

    def _local_hour(self, now: datetime) -> int:
        return now.astimezone(self._tz).hour

    def _stats(self, kind: str, topic: str, now: datetime) -> str:
        since = now - timedelta(days=STATS_DAYS)
        counts = self._store.outcome_counts(kind, since)
        total = ", ".join(f"{counts.get(o, 0)} {o}" for o in ("accepted", "deferred", "ignored", "declined"))
        on_topic = [o for t, o in self._store.topic_outcomes(since) if topic and similar(topic, t)]
        topic_part = (
            ", ".join(f"{on_topic.count(o)} {o}" for o in dict.fromkeys(on_topic)) if on_topic else "no history"
        )
        return f"for this kind: {total}; on this topic: {topic_part}"

    def _since_last(self, now: datetime) -> str:
        last = self._store.last_made()
        if last is None:
            return "none yet"
        hours = (now - last).total_seconds() / 3600.0
        return f"{hours:.0f} hour(s) ago" if hours >= 1 else "within the last hour"

    def _held(self, key: str, now: datetime) -> bool:
        until = self._store.hold_until(key)
        return until is not None and until > now

    # --------------------------------------------------------------- follow-ups

    async def followup_for_turn(
        self,
        text: str,
        candidates: list[Candidate],
        *,
        action_pending: bool = False,
        open_offer: bool = False,
    ) -> OpenOffer | None:
        """Advice, judgement and the bar, in that order. An OpenOffer if one should be made now."""
        if self._graph is None or self._judge is None or not candidates:
            return None
        now = self._now()
        gate = self._arbiter.permit(
            "followup", "", now, action_pending=action_pending, open_offer=open_offer
        )
        if not gate.ok:
            return None
        usable = [
            c
            for c in candidates
            if not self._held(f"node:{c.node.id}", now) and not self._arbiter.is_blocked("followup", c.node.topic)
        ]
        if not usable:
            return None
        notes = {}
        for c in usable:
            past = self._store.node_outcomes(c.node.id)
            if past:
                notes[c.node.id] = "earlier offers: " + ", ".join(past[-3:])
        advice = await self._graph.advise(text, usable, notes)
        if advice is None:
            return None
        return await self._decide_followup(advice, text, now)

    async def _decide_followup(self, advice: Advice, text: str, now: datetime) -> OpenOffer | None:
        assert self._judge is not None
        topic = advice.node.topic
        judgement = await self._judge.judge(
            kind="followup",
            topic=topic,
            description=f"{advice.node.gist} (open: {', '.join(advice.node.open) or 'nothing'}; "
            f"suggested step: {advice.step})",
            why=f"{advice.reason} (the advisor rates the benefit {advice.benefit:.2f})",
            stats=self._stats("followup", topic, now),
            since_last=self._since_last(now),
            busy=len(text.split()) <= 4,
            force_style="ask",
        )
        if judgement is None:
            return None
        bar = self._bars.value("followup", now)
        benefit = judgement.benefit
        hold_key = f"node:{advice.node.id}"
        if judgement.decision == "drop":
            self._store.set_hold(hold_key, now + timedelta(days=DROP_HOLD_DAYS))
            self._log_held("followup", topic, advice.step, benefit, bar, judgement, now, node_id=advice.node.id)
            return None
        if judgement.decision == "hold" or benefit < bar:
            self._store.set_hold(hold_key, now + timedelta(hours=judgement.retry_hours))
            self._log_held("followup", topic, advice.step, benefit, bar, judgement, now, node_id=advice.node.id)
            return None
        # Re-check the gate: a block or the rail may have changed while the models ran.
        if not self._arbiter.permit("followup", topic, now).ok:
            return None
        offer_id = self._store.add_offer(
            kind="followup", style="ask", topic=topic, step=advice.step, benefit=benefit, bar=bar,
            teaser=judgement.teaser, reason=judgement.reason, retry_hours=judgement.retry_hours,
            now=now, local_hour=self._local_hour(now), node_id=advice.node.id,
        )
        return OpenOffer(
            offer_id, "followup", "ask", topic, judgement.teaser, advice.step, node_id=advice.node.id,
            retry_hours=judgement.retry_hours,
        )

    def _log_held(
        self, kind: str, topic: str, step: str, benefit: float, bar: float, j: Judgement,
        now: datetime, *, node_id: int | None = None, signal_id: int | None = None,
    ) -> None:
        self._store.add_offer(
            kind=kind, style=j.style, topic=topic, step=step, benefit=benefit, bar=bar, teaser=j.teaser,
            reason=j.reason, retry_hours=j.retry_hours, now=now, local_hour=self._local_hour(now),
            outcome="held", node_id=node_id, signal_id=signal_id,
        )

    # ------------------------------------------------------------------ signals

    def add_signal(
        self,
        kind: str,
        summary: str,
        *,
        source: str,
        urgency: str | None = None,
        expires_at: datetime,
        topic_hint: str = "",
        safety: bool = False,
    ) -> int | None:
        """Take in a signal from any producer. None if it is unusable (empty, or already expired)."""
        now = self._now()
        summary = " ".join(summary.split())[:SIGNAL_SUMMARY_CHARS]
        if not summary or expires_at <= now:
            return None
        level = urgency if urgency in URGENCIES else ("medium" if kind == "weather" else "low")
        # The urgent path needs an allowlisted producer, a high urgency and a short expiry: all in code.
        urgent = (
            level == "high"
            and source in self._urgent_sources
            and expires_at - now <= timedelta(minutes=URGENT_MAX_MINUTES)
        )
        return self._store.add_signal(
            kind=kind, summary=summary, source=source, urgency=level, safety=safety or urgent,
            expires_at=expires_at, topic_hint=" ".join(topic_hint.split())[:60], urgent_path=urgent, now=now,
        )

    async def process_signals(self) -> int:
        """Judge new and due signals; mark worthwhile ones ready. Returns how many became ready."""
        if self._judge is None or not self.enabled:
            return 0
        async with self._lock:
            now = self._now()
            ready = 0
            for sig in self._store.signals(("new", "held")):
                if sig.expires_at <= now:
                    self._store.update_signal(sig.id, status="expired")
                    continue
                if sig.hold_until is not None and sig.hold_until > now:
                    continue
                if not self._arbiter.permit("timely", sig.topic, now, urgent=sig.urgent_path).ok:
                    continue
                if await self._judge_signal(sig, now):
                    ready += 1
            if ready and self._on_ready is not None:
                self._on_ready()
            return ready

    async def _judge_signal(self, sig: Signal, now: datetime) -> bool:
        assert self._judge is not None
        related = self._graph.connected(f"{sig.summary} {sig.topic_hint}") if self._graph else []
        approved = sig.source == RESEARCH_SOURCE  # an approved interest is a connection by construction
        context = ""
        if approved:
            context = f"The person has approved '{sig.topic}' as something they are interested in, and this was looked up for them while they were away."
        elif related:
            context = "Earlier conversations that may relate (what the person said or planned):\n" + "\n".join(
                f"- {c.node.topic}: {c.node.gist}" for c in related
            )
        else:
            context = "Nothing the person has said or approved seems to connect to this."
        judgement = await self._judge.judge(
            kind="timely",
            topic=sig.topic,
            description=f"A {sig.kind} signal from {sig.source} (urgency {sig.urgency}), "
            f"expires {sig.expires_at.astimezone(self._tz):%H:%M}: {sig.summary}",
            why="It arrived from outside the conversation.",
            stats=self._stats("timely", sig.topic, now),
            since_last=self._since_last(now),
            busy=False,
            context=context,
            force_style="tell" if (sig.safety or sig.urgent_path) else ("ask" if sig.kind == "research" else None),
        )
        if judgement is not None and sig.kind == "research":
            # Findings come from the web: only the topic is said until the user agrees.
            judgement = replace(judgement, style="ask", teaser=research_teaser(sig.topic))
        if judgement is None:
            # No usable answer (rail reached, model failure): look again shortly, not every minute.
            self._store.update_signal(sig.id, status="held", hold_until=min(sig.expires_at, now + timedelta(minutes=10)))
            return False
        bar = self._bars.value("timely", now) + (0.0 if (related or approved) else UNCONNECTED_EXTRA)
        if sig.urgent_path:
            bar = min(bar, 0.5)  # the producer's urgency has already been checked in code
        until = min(sig.expires_at, now + timedelta(hours=judgement.retry_hours))
        if judgement.decision == "drop":
            self._store.update_signal(sig.id, status="dropped", reason=judgement.reason)
            self._log_held("timely", sig.topic, "none", judgement.benefit, bar, judgement, now, signal_id=sig.id)
            return False
        # A finding already cleared the research bar when the topic was picked; the judge's own
        # offer/hold/drop (timing, interruption) decides the rest, without a second benefit bar.
        below = judgement.benefit < bar and sig.kind != "research"
        if judgement.decision == "hold" or below:
            self._store.update_signal(sig.id, status="held", hold_until=until, reason=judgement.reason)
            self._log_held("timely", sig.topic, "none", judgement.benefit, bar, judgement, now, signal_id=sig.id)
            return False
        self._store.update_signal(
            sig.id, status="ready", style=judgement.style, teaser=judgement.teaser,
            benefit=judgement.benefit, reason=judgement.reason, retry_hours=judgement.retry_hours,
        )
        return True

    def ready_notice(
        self, *, action_pending: bool = False, open_offer: bool = False, urgent_only: bool = False
    ) -> OpenOffer | None:
        """Take the next ready signal that may be said now, and count it as offered."""
        now = self._now()
        ready = self._store.signals(("ready",))
        ready.sort(key=lambda s: (not s.urgent_path, s.id))
        for sig in ready:
            if sig.expires_at <= now:
                self._store.update_signal(sig.id, status="expired")
                continue
            if urgent_only and not sig.urgent_path:
                continue
            gate = self._arbiter.permit(
                "timely", sig.topic, now, urgent=sig.urgent_path, action_pending=action_pending,
                open_offer=open_offer,
            )
            if not gate.ok:
                continue
            style = sig.style or "ask"
            offer_id = self._store.add_offer(
                kind="timely", style=style, topic=sig.topic, step="none", benefit=sig.benefit or 0.0,
                bar=self._bars.value("timely", now), teaser=sig.teaser or "", reason=sig.reason or "",
                retry_hours=sig.retry_hours or 6.0, now=now, local_hour=self._local_hour(now),
                signal_id=sig.id, urgent=sig.urgent_path,
            )
            self._store.update_signal(sig.id, status="offered")
            return OpenOffer(
                offer_id, "timely", style, sig.topic, sig.teaser or "", signal_id=sig.id,
                source=sig.source, detail=sig.summary, retry_hours=sig.retry_hours or 6.0,
            )
        return None

    def add_ready_signal(
        self, kind: str, summary: str, teaser: str, *, source: str, topic_hint: str, expires_at: datetime
    ) -> int | None:
        """A signal that is a question in its own right (it skips the judge, not the arbiter).

        For things the user must be asked, such as a proposed lesson, where "is it worth saying" is not
        for a model to decide. It is still said one at a time, at a quiet moment, and can be blocked.
        """
        sid = self.add_signal(kind, summary, source=source, urgency="low", expires_at=expires_at, topic_hint=topic_hint)
        if sid is None:
            return None
        self._store.update_signal(sid, status="ready", style="ask", teaser=teaser, benefit=1.0,
                                  reason="asked directly", retry_hours=72.0)
        if self._on_ready is not None:
            self._on_ready()
        return sid

    def on_resolve(self, source: str, hook: Callable[[Signal, str], None]) -> None:
        """Call ``hook(signal, outcome)`` when an offer made from this source's signal is answered."""
        self._hooks[source] = hook

    def has_ready(self) -> bool:
        return any(s.expires_at > self._now() for s in self._store.signals(("ready",)))

    def has_urgent_ready(self) -> bool:
        now = self._now()
        return any(s.urgent_path and s.expires_at > now for s in self._store.signals(("ready",)))

    def set_on_ready(self, callback: Callable[[], None] | None) -> None:
        """Called when a background pass makes a signal ready, so a client can speak at a quiet moment."""
        self._on_ready = callback

    def discard(self, offer: OpenOffer) -> None:
        """An offer that was decided but never said (the turn went another way). No effect on the bars."""
        self._store.resolve(offer.offer_id, "held", self._now())  # held rows do not count as made
        if offer.signal_id is not None:
            self._store.update_signal(offer.signal_id, status="ready")

    # ---------------------------------------------------------------- answers

    def resolve(self, offer: OpenOffer, outcome: str) -> None:
        """Record how the user answered: accepted, deferred, declined or ignored."""
        assert outcome in ("accepted", "deferred", "declined", "ignored"), outcome
        now = self._now()
        self._store.resolve(offer.offer_id, outcome, now)
        sig = self._store.get_signal(offer.signal_id) if offer.signal_id is not None else None
        if sig is None or sig.source not in self._hooks:
            self._bars.record(offer.kind, outcome, now)
        else:
            self._hooks[sig.source](sig, outcome)  # a question the user was asked, not an offer to learn from
        retry = now + timedelta(hours=offer.retry_hours)
        if offer.kind == "followup" and offer.node_id is not None:
            if outcome == "accepted" and self._graph is not None:
                self._graph.mark_done(offer.node_id, offer.step)
            elif outcome == "declined":
                if self._graph is not None:
                    self._graph.close_open(offer.node_id)
                self._store.set_hold(f"node:{offer.node_id}", now + timedelta(days=DROP_HOLD_DAYS))
            else:
                self._store.set_hold(f"node:{offer.node_id}", retry)
        elif offer.kind == "timely" and offer.signal_id is not None:
            sig = self._store.get_signal(offer.signal_id)
            if sig is not None and sig.source in self._hooks:
                # A question from a client that owns the follow-up (it asks again itself): never parked
                # as "held", where the judge would pick it up and weigh it like an ordinary signal.
                self._store.update_signal(offer.signal_id, status="done")
                return
            if sig is not None and sig.source == RESEARCH_SOURCE:
                self._bars.record("research", outcome, now)  # how welcome idle findings are
            if outcome == "deferred" and sig is not None and sig.expires_at > retry:
                self._store.update_signal(offer.signal_id, status="held", hold_until=retry)
            else:
                self._store.update_signal(
                    offer.signal_id, status="dropped" if outcome == "declined" else "done"
                )

    # ------------------------------------------------------------------ nudge

    def nudge_permitted(self, *, action_pending: bool = False, open_offer: bool = False) -> bool:
        return self._arbiter.permit(
            "nudge", "", self._now(), action_pending=action_pending, open_offer=open_offer
        ).ok

    def note_nudge(self) -> None:
        """Record that an interests nudge was added to a turn, so it counts against the day."""
        now = self._now()
        self._store.add_offer(
            kind="nudge", style="tell", topic="interests", step="none", benefit=0.0, bar=0.0,
            teaser="", reason="interests nudge", retry_hours=0.0, now=now,
            local_hour=self._local_hour(now), outcome="unresolved",
        )

    # ------------------------------------------------------------------ control

    def tools(self) -> list[LocalTool]:
        async def stop(args: dict, context: ToolContext) -> str:
            return self.stop(str(args.get("topic") or ""), str(args.get("kind") or ""))

        return [
            LocalTool(
                name=STOP_TOOL,
                description=(
                    "Stop making unprompted offers, when the user asks you to stop offering something "
                    "(for example examples, follow-ups, or heads-ups). Give a topic to stop offers about "
                    "one subject, a kind (followup, timely, nudge) to stop one sort of offer, or neither "
                    "to stop all offers. Use only on the user's request."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "topic": {"type": "string", "description": "A subject to stop offering about."},
                        "kind": {"type": "string", "enum": ["followup", "timely", "nudge"]},
                    },
                },
                handler=stop,
            )
        ]

    def stop(self, topic: str = "", kind: str = "") -> str:
        topic = " ".join(topic.split())[:60]
        kind = kind if kind in KINDS else ""
        now = self._now()
        if not topic and not kind:
            self._store.set_meta("enabled", "0")
            return "Offers are off. Tell the user you will stop, and that /offers on turns them back on."
        self._store.add_block(kind, topic, now)
        what = topic or f"{kind} offers"
        return f"Stopped offers about {what}. Tell the user you will stop."

    def set_enabled(self, on: bool) -> None:
        self._store.set_meta("enabled", "1" if on else "0")

    # ---------------------------------------------------------------- background

    def start_task(self, interval: float = 60.0) -> asyncio.Task[None]:
        async def loop() -> None:
            while True:
                try:
                    await self.process_signals()
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    log.warning("signal judging failed (%s); will retry", type(exc).__name__)
                await asyncio.sleep(interval)

        if self._task is None:
            self._task = asyncio.create_task(loop(), name="sutra-offers")
        return self._task

    async def stop_task(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
