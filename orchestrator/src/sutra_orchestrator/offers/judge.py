"""The judge: whether and when to speak up, and in what words. Code validates every field.

The model proposes a decision, a benefit score, a style and the exact words. Code
clamps the retry time, enforces what a "tell" may contain, and makes sure an "ask"
is one short question; a field that fails its check is replaced, never trusted.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from ..model import StructuredModel
from ..prompts import load_prompt

MIN_RETRY_HOURS = 1.0
MAX_RETRY_HOURS = 24.0 * 30
DEFAULT_RETRY_HOURS = 6.0
ASK_CHARS = 160
TELL_CHARS = 220
REASON_CHARS = 200

_ACTION = re.compile(
    r"\b(i'?ll|i will|i'?ve|i have|i'?m going to)\s+(book|order|cancel|send|pay|transfer|buy|change|"
    r"delete|reschedul|chang|fix|move|call|email|text)\w*\b|"
    r"\b(booked|ordered|cancell?ed|paid|transferred|rescheduled|purchased)\b",
    re.IGNORECASE,
)
_LINK = re.compile(r"https?://|www\.|\.com\b|\.org\b", re.IGNORECASE)
_SENTENCE_END = re.compile(r"[.!?]+(?:\s+|$)")


@dataclass(frozen=True)
class Judgement:
    decision: str  # "offer", "hold" or "drop"
    benefit: float
    style: str  # "ask" or "tell"
    teaser: str  # the words to say; already validated
    retry_hours: float
    reason: str


def fallback_ask(topic: str) -> str:
    topic = " ".join(topic.split())[:50]
    return f"Want to hear something useful about {topic}?" if topic else "Something came up, want to hear it?"


def valid_ask(text: str) -> bool:
    return (
        0 < len(text) <= ASK_CHARS
        and text.endswith("?")
        and text.count("?") == 1
        and len(_SENTENCE_END.findall(text)) == 1
        and not _LINK.search(text)
    )


def valid_tell(text: str) -> bool:
    return (
        0 < len(text) <= TELL_CHARS
        and "?" not in text
        and len(_SENTENCE_END.findall(text)) <= 2
        and not _ACTION.search(text)
        and not _LINK.search(text)
    )


def _unit(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0.0
    return min(1.0, max(0.0, float(value)))


def clamp_retry(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return DEFAULT_RETRY_HOURS
    return min(MAX_RETRY_HOURS, max(MIN_RETRY_HOURS, float(value)))


class Judge:
    def __init__(
        self,
        model: StructuredModel,
        *,
        spend: Callable[[], bool] | None = None,
        timeout: float = 30.0,
    ) -> None:
        self._model = model
        self._spend = spend or (lambda: True)
        self._timeout = timeout

    async def judge(
        self,
        *,
        kind: str,
        topic: str,
        description: str,
        why: str,
        stats: str,
        since_last: str,
        busy: bool,
        context: str = "",
        force_style: str | None = None,
    ) -> Judgement | None:
        """None means no usable answer (budget out, model failure, malformed): say nothing."""
        if not self._spend():
            return None
        lines = [
            f"Kind: {kind}",
            f"Topic: {topic}",
            f"Candidate: {description}",
            f"Why it might help: {why}",
            f"How the person has reacted before: {stats}",
            f"Last offer: {since_last}",
            f"The person seems busy with a quick task: {'yes' if busy else 'no'}",
        ]
        if context:
            lines += ["", context]
        raw = await asyncio.wait_for(
            self._model.structured(
                name="judgement", system=load_prompt("offers_judge.md"), user="\n".join(lines)
            ),
            timeout=self._timeout,
        )
        if not isinstance(raw, dict) or raw.get("decision") not in ("offer", "hold", "drop"):
            return None
        style = force_style or ("tell" if raw.get("style") == "tell" and kind == "timely" else "ask")
        teaser = " ".join(str(raw.get("teaser") or "").split())
        if style == "tell" and not valid_tell(teaser):
            style, teaser = "ask", fallback_ask(topic)
        elif style == "ask" and not valid_ask(teaser):
            teaser = fallback_ask(topic)
        reason = " ".join(str(raw.get("reason") or "").split())[:REASON_CHARS] or "no reason given"
        return Judgement(
            raw["decision"], _unit(raw.get("benefit")), style, teaser, clamp_retry(raw.get("retry_after_hours")), reason
        )
