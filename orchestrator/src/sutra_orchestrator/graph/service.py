"""The episode graph as the rest of Sutra sees it.

Writes: turns are observed after the fact; an episode closes on a subject change,
an idle gap or the end of a session, and is then summarised and linked in the
background. Reads: candidates for a piece of text, and advice from a tools-off
subagent that the offer judge weighs. Nothing here ever speaks to the user.
"""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from ..memstore.textutil import tokens
from ..model import StructuredModel
from ..prompts import load_prompt
from .retrieve import Candidate, LexicalRetriever, Retriever
from .store import EDGE_TYPES, MODES, STEPS, GraphStore, Node

log = logging.getLogger("sutra_orchestrator")

IDLE_MINUTES = 30  # an episode ends after this much quiet; also "the same conversation"
MAX_TURNS = 10
TOPIC_CHARS = 60
GIST_CHARS = 300
REASON_CHARS = 200
REPLY_CHARS = 600
UTTERANCE_CHARS = 300
MERGE_STRENGTH = 0.8
SAME_SUBJECT = 0.5  # overlap at or above this means the subject has not changed


@dataclass(frozen=True)
class Advice:
    node: Node
    benefit: float
    reason: str
    step: str  # one of STEPS or "none"


@dataclass
class _Turn:
    ts: datetime
    user: str
    reply: str | None


def _clip(value: Any, limit: int) -> str | None:
    if not isinstance(value, str):
        return None
    text = " ".join(value.split()).strip()
    return text[:limit] if text else None


def _unit(value: Any, default: float = 0.0) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return default
    return min(1.0, max(0.0, float(value)))


def _coefficient(a: set[str], b: set[str]) -> float:
    return len(a & b) / min(len(a), len(b)) if a and b else 0.0


class GraphService:
    def __init__(
        self,
        store: GraphStore,
        model: StructuredModel,
        *,
        retriever: Retriever | None = None,
        exclude_tool_prefixes: tuple[str, ...] = ("finanxe_",),
        spend: Callable[[], bool] | None = None,
        timeout: float = 30.0,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._store = store
        self._model = model
        self._retriever: Retriever = retriever or LexicalRetriever(store)
        self._exclude = exclude_tool_prefixes
        self._spend = spend or (lambda: True)
        self._timeout = timeout
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._buffer: list[_Turn] = []
        self._recent: deque[str] = deque(maxlen=3)
        self._last_check: set[str] = set()
        self._tasks: set[asyncio.Task[None]] = set()
        self._listeners: list[Callable[[list[str], datetime], Awaitable[None]]] = []

    def add_listener(self, listener: "Callable[[list[str], datetime], Awaitable[None]]") -> None:
        """Call ``listener(user_lines, when)`` whenever an episode closes (the user's words only)."""
        self._listeners.append(listener)

    @property
    def store(self) -> GraphStore:
        return self._store

    @property
    def retriever(self) -> Retriever:
        return self._retriever

    # ---------------------------------------------------------------- observe

    def observe(
        self, utterance: str, reply: str, tools: list[str], *, low_confidence: bool = False, private: bool = False
    ) -> None:
        """Note one finished turn. Cheap and synchronous; model work happens in the background.

        A private turn (the user just wanted to talk) is not remembered as a topic at all."""
        if low_confidence or private:
            return
        if any(t.startswith(p) for t in tools for p in self._exclude if p):
            return
        text = " ".join(utterance.split())[:UTTERANCE_CHARS]
        if len(tokens(text)) < 2:
            return
        now = self._now()
        if self._buffer and self._subject_changed(text, now):
            self.close_episode()
        # The assistant's reply counts only on turns that used no tool.
        self._buffer.append(_Turn(now, text, None if tools else " ".join(reply.split())[:REPLY_CHARS]))
        self._recent.append(text)

    def _subject_changed(self, text: str, now: datetime) -> bool:
        if now - self._buffer[-1].ts > timedelta(minutes=IDLE_MINUTES) or len(self._buffer) >= MAX_TURNS:
            return True
        new = set(tokens(text))
        seen = {t for turn in self._buffer for t in tokens(turn.user)}
        return len(new) >= 3 and not (new & seen)

    def close_episode(self) -> None:
        """End the current episode (subject change, session end) and summarise it in the background."""
        turns, self._buffer = self._buffer, []
        if not turns:
            return
        task = asyncio.ensure_future(self._finish(turns))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def flush(self) -> None:
        if self._tasks:
            await asyncio.gather(*list(self._tasks), return_exceptions=True)

    # ------------------------------------------------------- build a node, link

    async def _finish(self, turns: list[_Turn]) -> None:
        for listener in self._listeners:
            try:
                await listener([t.user for t in turns], turns[0].ts)
            except asyncio.CancelledError:
                raise
            except Exception:
                log.debug("an episode listener failed", exc_info=True)
        try:
            await self._build(turns)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.warning("episode summary failed (%s); it was not kept", type(exc).__name__)

    async def _build(self, turns: list[_Turn]) -> None:
        if not self._spend():
            return
        lines: list[str] = []
        for t in turns:
            lines.append(f"Person: {t.user}")
            if t.reply:
                lines.append(f"Assistant: {t.reply}")
        raw = await asyncio.wait_for(
            self._model.structured(
                name="episode", system=load_prompt("graph_episode.md"), user="\n".join(lines)
            ),
            timeout=self._timeout,
        )
        episode = self._valid_episode(raw)
        if episode is None:
            return
        topic, gist, mode, open_items, entities = episode
        now = self._now()
        candidates = self._retriever.candidates(
            " ".join([topic, gist, *entities]), now=now, exclude_touched_after=None
        )
        edges = await self._link(topic, gist, open_items, candidates) if candidates else []
        merge = next(
            (e for e in edges if e[1] == "same_topic" and e[2] >= MERGE_STRENGTH), None
        )
        if merge is not None:
            target = merge[0]
            self._store.merge_into(target.id, gist, open_items, entities, now)
            for other, type_, strength, reason in edges:
                if other.id != target.id:
                    self._store.add_edge(target.id, other.id, type_, strength, reason, now)
        else:
            node_id = self._store.add_node(topic, gist, mode, open_items, entities, now)
            for other, type_, strength, reason in edges:
                self._store.add_edge(node_id, other.id, type_, strength, reason, now)
                self._store.touch(other.id, now)
        self._store.decay(now)

    @staticmethod
    def _valid_episode(raw: Any) -> tuple[str, str, str, list[str], list[str]] | None:
        if not isinstance(raw, dict) or raw.get("keep") is not True:
            return None
        topic, gist = _clip(raw.get("topic"), TOPIC_CHARS), _clip(raw.get("gist"), GIST_CHARS)
        if not topic or not gist:
            return None
        mode = raw.get("mode") if raw.get("mode") in MODES else "asked"
        open_raw = raw.get("open") if isinstance(raw.get("open"), list) else []
        open_items = [s for s in dict.fromkeys(open_raw) if s in STEPS]
        ent_raw = raw.get("entities") if isinstance(raw.get("entities"), list) else []
        entities = [e for e in (_clip(x, 30) for x in ent_raw[:5]) if e]
        return topic, gist, mode, open_items, entities

    async def _link(
        self, topic: str, gist: str, open_items: list[str], candidates: list[Candidate]
    ) -> list[tuple[Node, str, float, str]]:
        if not self._spend():
            return []
        lines = [f"New episode: {topic}. {gist}", "", "Earlier episodes:"]
        for i, c in enumerate(candidates, 1):
            lines.append(f"[{i}] {c.node.topic}. {c.node.gist}")
        raw = await asyncio.wait_for(
            self._model.structured(
                name="links", system=load_prompt("graph_links.md"), user="\n".join(lines)
            ),
            timeout=self._timeout,
        )
        items = raw.get("edges") if isinstance(raw, dict) else None
        out: list[tuple[Node, str, float, str]] = []
        for item in items if isinstance(items, list) else []:
            if not isinstance(item, dict):
                continue
            n, type_ = item.get("target"), item.get("type")
            reason = _clip(item.get("reason"), REASON_CHARS)
            if (
                isinstance(n, int)
                and not isinstance(n, bool)
                and 1 <= n <= len(candidates)
                and type_ in EDGE_TYPES
                and reason
            ):
                out.append((candidates[n - 1].node, type_, _unit(item.get("strength")), reason))
        return out

    # ----------------------------------------------------------------- advice

    def check_candidates(self, utterance: str, *, low_confidence: bool = False) -> list[Candidate]:
        """Candidates worth an advice call for this utterance, or [] when none should be made.

        Cheap code tests first: a call is made only if the subject has changed since the last
        check and the retriever finds something. Nodes touched within the idle gap are skipped:
        they belong to the conversation still going on.
        """
        if low_confidence:
            return []
        text = " ".join(utterance.split())
        words = set(tokens(text))
        if len(words) < 3 or _coefficient(words, self._last_check) >= SAME_SUBJECT:
            return []
        self._last_check = words
        now = self._now()
        context = " ".join([text, *self._recent])
        return self._retriever.candidates(
            context, now=now, exclude_touched_after=now - timedelta(minutes=IDLE_MINUTES)
        )

    def connected(self, text: str) -> list[Candidate]:
        """Nodes that really match this text by words (no fallbacks), for judging outside signals."""
        return self._retriever.candidates(text, now=self._now(), lexical_only=True, limit=4)

    async def advise(
        self, utterance: str, candidates: list[Candidate], notes: dict[int, str] | None = None
    ) -> Advice | None:
        """Ask the relatedness subagent. None means nothing is worth following up."""
        if not candidates or not self._spend():
            return None
        notes = notes or {}
        now = self._now()
        lines = [f"Now: {' '.join(utterance.split())[:UTTERANCE_CHARS]}"]
        for i, before in enumerate(list(self._recent)[-2:], 1):
            lines.append(f"Before ({i}): {before}")
        lines += ["", "Earlier episodes:"]
        for i, c in enumerate(candidates, 1):
            n = c.node
            days = max((now - n.last_touched).days, 0)
            extra = f"; {notes[n.id]}" if n.id in notes else ""
            lines.append(
                f"[{i}] {n.topic}. {n.gist} (open: {', '.join(n.open) or 'nothing'}; "
                f"{'today' if days == 0 else f'{days} day(s) ago'}{extra})"
            )
        raw = await asyncio.wait_for(
            self._model.structured(
                name="advice", system=load_prompt("graph_advice.md"), user="\n".join(lines)
            ),
            timeout=self._timeout,
        )
        if not isinstance(raw, dict):
            return None
        n = raw.get("choice")
        if not isinstance(n, int) or isinstance(n, bool) or not 1 <= n <= len(candidates):
            return None  # none, or a number that was not offered
        reason = _clip(raw.get("reason"), REASON_CHARS)
        if not reason:
            return None
        step = raw.get("step") if raw.get("step") in (*STEPS, "none") else "none"
        return Advice(candidates[n - 1].node, _unit(raw.get("benefit")), reason, step)

    # ------------------------------------------------------------- progress

    def mark_done(self, node_id: int, step: str) -> None:
        node = self._store.get(node_id)
        if node is None:
            return
        self._store.set_open(node_id, [s for s in node.open if s != step])
        self._store.touch(node_id, self._now())

    def close_open(self, node_id: int) -> None:
        self._store.set_open(node_id, [])
