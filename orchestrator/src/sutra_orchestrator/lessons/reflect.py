"""Finding lessons: corrections from the user's own exchanges, and outcome counts from offers.

Nothing here has an effect. Both sources only create proposals, each checked in code.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol

from ..classifier import AFFIRMATIVES, NEGATIVES
from ..interests.reflect import similar
from ..memstore.textutil import normalize
from ..model import StructuredModel
from ..prompts import load_prompt
from . import rules
from .store import Lesson, LessonStore

WINDOW_DAYS = 14
MAX_PAIRS = 120
REPLY_CHARS = 300
UTTERANCE_CHARS = 200
PAIR_GAP = timedelta(minutes=30)
MAX_NEW_PER_RUN = 3
MAX_PENDING = 5
OUTCOME_DAYS = 60
OUTCOME_MIN = 3  # declined or ignored, with none accepted: the evidence rule, fixed and inspectable
_TRIVIAL = AFFIRMATIVES | NEGATIVES


class ExchangeSource(Protocol):
    def recent_exchanges(
        self, since: datetime, limit: int = 400
    ) -> list[tuple[str, datetime, str, str | None, list[str]]]: ...


class OutcomeSource(Protocol):
    def kind_topic_outcomes(self, since: datetime) -> list[tuple[str, str, str]]: ...


@dataclass
class RunResult:
    read: int = 0
    created: int = 0
    skipped: str = ""


@dataclass(frozen=True)
class Pair:
    ref: str
    ts: datetime
    reply: str
    utterance: str


class Reflector:
    def __init__(
        self,
        source: ExchangeSource | None,
        store: LessonStore,
        model: StructuredModel,
        *,
        exclude_tool_prefixes: tuple[str, ...] = ("finanxe_",),
        timeout: float = 60.0,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._source = source
        self._store = store
        self._model = model
        self._exclude = exclude_tool_prefixes
        self._timeout = timeout
        self._now = now or (lambda: datetime.now(timezone.utc))

    def _excluded(self, tools: list[str]) -> bool:
        return any(t.startswith(p) for t in tools for p in self._exclude if p)

    def pairs(self) -> list[Pair]:
        """An assistant reply followed by the user's next words. Only no-tool replies; never finance."""
        if self._source is None:
            return []
        rows = self._source.recent_exchanges(self._now() - timedelta(days=WINDOW_DAYS))
        out: list[Pair] = []
        for prev, cur in zip(rows, rows[1:]):
            _, pts, _, reply, ptools = prev
            cid, cts, utterance, _, ctools = cur
            if not reply or ptools or self._excluded(ptools) or self._excluded(ctools):
                continue
            if cts - pts > PAIR_GAP:
                continue
            text = " ".join(utterance.split())
            if len(text.split()) < 2 or normalize(text) in _TRIVIAL:
                continue
            out.append(Pair(cid, cts, " ".join(reply.split())[:REPLY_CHARS], text[:UTTERANCE_CHARS]))
        return out[-MAX_PAIRS:]

    async def run(self, last_run: datetime | None) -> RunResult:
        """One pass. Raises on model failure; creates nothing in that case."""
        pairs = self.pairs()
        fresh = [p for p in pairs if last_run is None or p.ts > last_run]
        if not fresh:
            return RunResult(read=len(pairs), skipped="no new exchanges")
        active = [l for l in self._store.list(("active",)) if l.effect == "guidance"]
        raw = await asyncio.wait_for(
            self._model.structured(
                name="lesson_reflect", system=load_prompt("lessons.md"), user=self._message(active, pairs)
            ),
            timeout=self._timeout,
        )
        return RunResult(read=len(pairs), created=self._apply(raw, active, pairs))

    @staticmethod
    def _message(active: list[Lesson], pairs: list[Pair]) -> str:
        lines = ["Lessons the assistant already follows:"]
        lines += [f"[{i}] {l.text}" for i, l in enumerate(active, 1)] or ["(none)"]
        lines += ["", "Exchanges:"]
        for i, p in enumerate(pairs, 1):
            lines.append(f"[{i}] ({p.ts:%Y-%m-%d}) Assistant: {p.reply}\n    Person: {p.utterance}")
        return "\n".join(lines)

    def _apply(self, raw: Any, active: list[Lesson], pairs: list[Pair]) -> int:
        items = raw.get("items") if isinstance(raw, dict) else raw
        if not isinstance(items, list):
            return 0
        now = self._now()
        known = self._store.list()
        pending = sum(1 for l in known if l.status == "proposed")
        created = 0
        for item in items[:MAX_NEW_PER_RUN]:
            if not isinstance(item, dict):
                continue
            proposal = rules.guidance(item.get("text"))
            evidence = self._evidence(item.get("evidence"), pairs)
            n = item.get("recurrence_of")
            target = (
                active[n - 1]
                if isinstance(n, int) and not isinstance(n, bool) and 1 <= n <= len(active)
                else None
            )
            if target is not None and evidence:
                self._store.record_recurrence(target.id)  # it is not working: say so, never pile up copies
            if proposal is None or not evidence or created >= MAX_NEW_PER_RUN:
                continue
            # Never propose anything like a lesson the user has seen and decided on, or already follows.
            if any(similar(proposal.text, l.text) or similar(l.text, proposal.text) for l in known if l.status != "superseded"):
                continue
            if pending + created >= MAX_PENDING:
                continue
            lesson_id = self._store.add(
                proposal.text, "guidance", "correction", now, revises_id=target.id if target else None
            )
            for pair in evidence:
                self._store.add_evidence(lesson_id, pair.ref, pair.utterance, pair.ts)
            created += 1
        return created

    @staticmethod
    def _evidence(raw: Any, pairs: list[Pair]) -> list[Pair]:
        out: list[Pair] = []
        for n in raw if isinstance(raw, list) else []:
            if isinstance(n, int) and not isinstance(n, bool) and 1 <= n <= len(pairs) and pairs[n - 1] not in out:
                out.append(pairs[n - 1])
        return out


def outcome_proposals(source: OutcomeSource, store: LessonStore, now: datetime) -> int:
    """Block lessons from counts alone, no model: a kind or topic that keeps being declined or ignored.

    At least three declined or ignored offers in 60 days and none accepted. A kind-wide lesson covers
    its topics, so topic lessons are only made for a kind that has some acceptance.
    """
    rows = source.kind_topic_outcomes(now - timedelta(days=OUTCOME_DAYS))
    known = store.list()
    created = 0

    def exists(kind: str, topic: str) -> bool:
        return any(
            l.effect == "block" and l.kind == kind and l.status != "superseded"
            and ((not topic and not l.topic) or (topic and l.topic and similar(topic, l.topic)))
            for l in known
        )

    names = {"followup": "follow-ups", "timely": "heads-ups and findings"}
    for kind in ("followup", "timely"):
        mine = [(t, o) for k, t, o in rows if k == kind]
        no = sum(1 for _, o in mine if o in ("declined", "ignored"))
        yes = sum(1 for _, o in mine if o == "accepted")
        if no >= OUTCOME_MIN and yes == 0:
            if not exists(kind, ""):
                lid = store.add(f"Stop offering {names[kind]}", "block", "outcomes", now, kind=kind)
                store.add_evidence(lid, f"{kind}:all", f"{no} declined or ignored, none accepted in {OUTCOME_DAYS} days", now)
                created += 1
            continue
        topics: list[str] = []
        for t, _ in mine:
            if t and not any(similar(t, u) for u in topics):
                topics.append(t)
        for topic in topics:
            same = [o for t, o in mine if similar(topic, t) or similar(t, topic)]
            no_t = sum(1 for o in same if o in ("declined", "ignored"))
            if no_t >= OUTCOME_MIN and "accepted" not in same and not exists(kind, topic):
                text = rules.clean_text(f"Stop offering {names[kind]} about {topic}")
                if text:
                    lid = store.add(text, "block", "outcomes", now, kind=kind, topic=topic[:60])
                    store.add_evidence(lid, f"{kind}:{topic}", f"{no_t} declined or ignored, none accepted in {OUTCOME_DAYS} days", now)
                    created += 1
    return created
