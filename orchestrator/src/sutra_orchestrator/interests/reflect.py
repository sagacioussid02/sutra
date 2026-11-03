"""Reflection: read the user's own recent words, propose interests, validate in code.

The model only suggests. Everything it returns is checked here: evidence must be
real, targets must exist, a claimed change must resemble what it says changed,
and nothing becomes active without the user's approval.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol

from ..classifier import AFFIRMATIVES, NEGATIVES
from ..memstore.textutil import normalize, overlap
from ..model import InterestModel
from ..prompts import load_prompt
from .store import InterestRow, InterestStore

log = logging.getLogger("sutra_orchestrator")

MAX_UTTERANCES = 150
UTTERANCE_CHARS = 200
MAX_NEW_PER_RUN = 3
MAX_PENDING = 5
LABEL_CHARS = 60
SIMILAR = 0.6
_TRIVIAL = AFFIRMATIVES | NEGATIVES
RELATIONS = ("new", "strengthens", "changes")


class EpisodeSource(Protocol):
    def recent_user_episodes(
        self, since: datetime, limit: int = 400
    ) -> list[tuple[str, datetime, str, list[str]]]: ...


@dataclass
class RunResult:
    read: int = 0
    created: int = 0
    skipped: str = ""  # why no model call was made


def similar(a: str, b: str) -> bool:
    """Two topic labels that mean the same thing, judged by words."""
    na, nb = normalize(a), normalize(b)
    return bool(na) and (na == nb or overlap(a, b) >= SIMILAR)


def clean_label(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    label = " ".join(value.split()).strip(" .,;")
    return label if 2 <= len(label) <= LABEL_CHARS else None


class Reflector:
    def __init__(
        self,
        source: EpisodeSource,
        store: InterestStore,
        model: InterestModel,
        *,
        window_days: int = 30,
        exclude_tool_prefixes: tuple[str, ...] = ("finanxe_",),
        timeout: float = 60.0,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._source = source
        self._store = store
        self._model = model
        self._window = timedelta(days=window_days)
        self._exclude = exclude_tool_prefixes
        self._timeout = timeout
        self._now = now or (lambda: datetime.now(timezone.utc))

    # ----------------------------------------------------------------- input

    def eligible(self) -> list[tuple[str, datetime, str]]:
        """(id, time, text) of utterances reflection may read, oldest first."""
        start = self._now() - self._window
        rows = self._source.recent_user_episodes(start)
        out: list[tuple[str, datetime, str]] = []
        for episode_id, ts, utterance, tools in rows:
            if any(t.startswith(p) for t in tools for p in self._exclude if p):
                continue
            text = " ".join(utterance.split())
            if not text or normalize(text) in _TRIVIAL:
                continue
            out.append((episode_id, ts, text[:UTTERANCE_CHARS]))
        out.sort(key=lambda r: r[1])
        return out[-MAX_UTTERANCES:]

    # ------------------------------------------------------------------- run

    async def run(self, last_run: datetime | None) -> RunResult:
        """One reflection pass. Raises on model failure; creates nothing in that case."""
        eligible = self.eligible()
        fresh = [e for e in eligible if last_run is None or e[1] > last_run]
        if not fresh:
            return RunResult(read=len(eligible), skipped="no new utterances")
        known = [
            r for r in self._store.list(("active", "proposed", "muted")) if r.status != "superseded"
        ]
        raw = await asyncio.wait_for(
            self._model.reflect_interests(
                system=load_prompt("interests.md"), user=self._message(known, eligible)
            ),
            timeout=self._timeout,
        )
        created = self._apply(raw, known, eligible)
        return RunResult(read=len(eligible), created=created)

    @staticmethod
    def _message(known: list[InterestRow], eligible: list[tuple[str, datetime, str]]) -> str:
        lines = ["Known interests:"]
        lines += [f"[{i}] {k.topic}" for i, k in enumerate(known, 1)] or ["(none)"]
        lines += ["", "Utterances:"]
        lines += [f"[{i}] ({ts:%Y-%m-%d}) {text}" for i, (_, ts, text) in enumerate(eligible, 1)]
        return "\n".join(lines)

    # -------------------------------------------------------------- validate

    def _apply(
        self,
        raw: Any,
        known: list[InterestRow],
        eligible: list[tuple[str, datetime, str]],
    ) -> int:
        if not isinstance(raw, list):
            return 0
        now = self._now()
        pending = sum(1 for r in self._store.list(("proposed",)))
        created = 0
        for item in raw[:MAX_NEW_PER_RUN]:
            if not isinstance(item, dict):
                continue
            label = clean_label(item.get("label"))
            evidence = self._evidence(item.get("evidence"), eligible)
            if label is None or not evidence:
                continue
            relation = item.get("relation") if item.get("relation") in RELATIONS else "new"
            target = self._target(item.get("target"), known) if relation != "new" else None
            if relation != "new" and target is None:
                relation = "new"
            if relation == "changes":
                before, now_text = clean_label(item.get("before")), clean_label(item.get("now"))
                if target.status != "active" or not before or not now_text or not similar(before, target.topic):
                    relation = "new"
                else:
                    if similar(now_text, target.topic):
                        relation = "strengthens"  # nothing actually changed
                    else:
                        label = now_text
            if relation == "strengthens":
                self._add_evidence(target.id, evidence, now)
                continue
            # new or changes: compare with everything the user has already seen or decided
            match = next(
                (r for r in self._store.list() if r.status != "superseded" and similar(label, r.topic)),
                None,
            )
            if match is not None:
                if match.status in ("active", "proposed") and relation == "new":
                    self._add_evidence(match.id, evidence, now)
                continue  # rejected, muted, or already covered: never proposed again
            if created >= MAX_NEW_PER_RUN or pending + created >= MAX_PENDING:
                continue
            if relation == "changes":
                new_id = self._store.add(
                    label,
                    status="proposed",
                    source="reflection",
                    now=now,
                    revises_id=target.id,
                    change_before=target.topic,
                    change_now=label,
                    offer=True,
                )
            else:
                new_id = self._store.add(label, status="proposed", source="reflection", now=now, offer=True)
            self._add_evidence(new_id, evidence, now)
            created += 1
        return created

    @staticmethod
    def _evidence(raw: Any, eligible: list[tuple[str, datetime, str]]) -> list[tuple[str, datetime, str]]:
        out: list[tuple[str, datetime, str]] = []
        if not isinstance(raw, list):
            return out
        for n in raw:
            if isinstance(n, int) and not isinstance(n, bool) and 1 <= n <= len(eligible):
                if eligible[n - 1] not in out:
                    out.append(eligible[n - 1])
        return out

    @staticmethod
    def _target(raw: Any, known: list[InterestRow]) -> InterestRow | None:
        if isinstance(raw, int) and not isinstance(raw, bool) and 1 <= raw <= len(known):
            row = known[raw - 1]
            return row if row.status in ("active", "proposed") else None
        return None

    def _add_evidence(self, interest_id: int, evidence: list[tuple[str, datetime, str]], now: datetime) -> None:
        added = [ts for episode_id, ts, text in evidence if self._store.add_evidence(interest_id, episode_id, text, ts)]
        row = self._store.get(interest_id)
        if added and row is not None and row.status == "active":
            self._store.touch(interest_id, max(added))
