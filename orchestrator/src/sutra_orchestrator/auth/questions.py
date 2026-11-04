"""Writing a one-time question from a real fact. Code checks what the model returns; none of it is trusted."""

from __future__ import annotations

import asyncio
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from ..model import StructuredModel
from ..personality import rules
from ..prompts import load_prompt
from .store import Fact

MAX_QUESTION_CHARS = 140
MAX_CANDIDATES = 12


@dataclass(frozen=True)
class Question:
    ref: str
    text: str
    answer: str
    kind: str


def _norm(text: str) -> str:
    return " ".join(re.sub(r"[^\wऀ-ॿ\s]", " ", text.lower()).split())


def check(raw: Any, candidates: list[Fact], names: list[str]) -> Question | None:
    """A grounded, safe question, or None. Every rule here is code, not a request to the model."""
    if not isinstance(raw, dict):
        return None
    n = raw.get("fact")
    if not isinstance(n, int) or isinstance(n, bool) or not 1 <= n <= len(candidates):
        return None
    fact = candidates[n - 1]
    question = " ".join(str(raw.get("question") or "").split())
    answer = " ".join(str(raw.get("answer") or "").split()).strip(" .,;:!?")
    if not question or not answer or len(question) > MAX_QUESTION_CHARS or not question.endswith("?"):
        return None
    if question.count("?") != 1 or len(re.findall(r"[.!?](?:\s|$)", question)) != 1:
        return None
    if _norm(answer) not in _norm(fact.text):  # the answer must be in the fact's own words
        return None
    if _norm(answer) in _norm(question):  # and the question must not give it away
        return None
    if len(answer.split()) > 6:
        return None
    if rules.heavy(question) or rules.upset(question):
        return None
    lowered = question.lower()
    if any(re.search(rf"(?<!\w){re.escape(p.lower())}(?!\w)", lowered) for p in names if p):
        return None
    return Question(fact.ref, question, answer, fact.kind)


class QuestionWriter:
    def __init__(self, model: StructuredModel, *, spend: Callable[[], bool] | None = None, timeout: float = 20.0) -> None:
        self._model = model
        self._spend = spend or (lambda: True)
        self._timeout = timeout

    async def write(self, candidates: list[Fact], names: list[str], now: datetime, attempts: int = 3) -> Question | None:
        """One question from the candidates (typed facts first, then newest), or None."""
        pool = candidates[:MAX_CANDIDATES]
        for _ in range(attempts):
            if not pool or not self._spend():
                return None
            lines = [f"Today is {now:%A, %B %d}."]
            for i, f in enumerate(pool, 1):
                lines.append(f"[{i}] ({f.kind}, {f.ts:%A}) {f.text}")
            try:
                raw = await asyncio.wait_for(
                    self._model.structured(
                        name="auth_question", system=load_prompt("auth_question.md"), user="\n".join(lines)
                    ),
                    timeout=self._timeout,
                )
            except (asyncio.TimeoutError, Exception):
                return None
            q = check(raw, pool, names)
            if q is not None:
                return q
            n = raw.get("fact") if isinstance(raw, dict) else None
            if isinstance(n, int) and not isinstance(n, bool) and 1 <= n <= len(pool):
                pool = [f for i, f in enumerate(pool, 1) if i != n]  # a bad fact is not tried again
        return None
