"""The picker: which topic, if any, is worth a small research run. Code checks everything it returns.

The model only sees approved interests and the topics (never the gists) of recent plans,
so it has no private detail to copy into the brief; code checks the brief anyway.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from ..interests.reflect import similar
from ..model import StructuredModel
from ..prompts import load_prompt

BRIEF_MIN, BRIEF_MAX = 20, 200
MIN_REVISIT_DAYS, MAX_REVISIT_DAYS = 3, 90
PLAN_DAYS = 60
KINDS = ("whats_new", "upcoming", "compare", "how_to")

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_DIGITS = re.compile(r"\d[\d\s().-]{6,}\d")  # phone numbers and other long digit runs
_MONEY = re.compile(r"[$€£¥]\s?\d|\b\d[\d,.]*\s?(?:dollars?|usd|eur|euros?|pounds?|rupees?|inr)\b", re.IGNORECASE)
_URL = re.compile(r"https?://|www\.|\b\w+\.(?:com|org|net|io)\b", re.IGNORECASE)


@dataclass(frozen=True)
class Topic:
    label: str
    source: str  # "interest" or "plan"
    note: str  # what the picker is told besides the label


@dataclass(frozen=True)
class Pick:
    topic: Topic
    brief: str
    kind: str
    value: float
    revisit_days: float


def brief_problem(brief: str, blocked_words: list[str] | None = None) -> str | None:
    """Why a brief may not leave the machine, or None if it may."""
    if not BRIEF_MIN <= len(brief) <= BRIEF_MAX:
        return "length"
    for name, pattern in (("email", _EMAIL), ("number", _DIGITS), ("money", _MONEY), ("url", _URL)):
        if pattern.search(brief):
            return name
    lowered = brief.lower()
    for word in blocked_words or []:
        if word and word.lower() in lowered:
            return "blocked topic"
    return None


class Picker:
    def __init__(self, model: StructuredModel, *, timeout: float = 30.0,
                 spend: Callable[[], bool] | None = None) -> None:
        self._model = model
        self._timeout = timeout
        self._spend = spend or (lambda: True)

    async def pick(
        self, topics: list[Topic], today: datetime, earlier: list[str], tz_date: str
    ) -> Pick | None:
        if not topics or not self._spend():
            return None
        lines = [f"Today is {tz_date}.", "", "Topics:"]
        lines += [f"[{i}] {t.label} ({t.note})" for i, t in enumerate(topics, 1)]
        lines += ["", "Earlier research:"] + (earlier or ["(none)"])
        raw = await asyncio.wait_for(
            self._model.structured(
                name="idle_pick", system=load_prompt("idle_picker.md"), user="\n".join(lines)
            ),
            timeout=self._timeout,
        )
        if not isinstance(raw, dict):
            return None
        n = raw.get("choice")
        if not isinstance(n, int) or isinstance(n, bool) or not 1 <= n <= len(topics):
            return None  # none, or a number that was not offered
        brief = " ".join(str(raw.get("brief") or "").split())
        value = raw.get("value")
        value = 0.0 if isinstance(value, bool) or not isinstance(value, (int, float)) else min(1.0, max(0.0, float(value)))
        revisit = raw.get("revisit_after_days")
        revisit = (
            MIN_REVISIT_DAYS
            if isinstance(revisit, bool) or not isinstance(revisit, (int, float))
            else min(MAX_REVISIT_DAYS, max(MIN_REVISIT_DAYS, float(revisit)))
        )
        kind = raw.get("kind") if raw.get("kind") in KINDS else "whats_new"
        return Pick(topics[n - 1], brief, kind, value, revisit)


def reactions(topic: str, outcomes: list[tuple[str, str]]) -> str:
    mine = [o for t, o in outcomes if similar(topic, t) or similar(t, topic)]
    if not mine:
        return "no reactions yet"
    return ", ".join(f"{mine.count(o)} {o}" for o in dict.fromkeys(mine))
