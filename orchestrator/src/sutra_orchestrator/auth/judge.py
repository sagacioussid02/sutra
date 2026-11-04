"""Deciding whether an answer is right. Fails closed; the reply is data, never instructions."""

from __future__ import annotations

import asyncio
import re
from collections.abc import Callable

from ..model import StructuredModel
from ..prompts import load_prompt

MATCH, NO_MATCH, UNSURE = "match", "no_match", "unsure"
MAX_REPLY_WORDS = 40
_ARTICLES = {"the", "a", "an"}


def _norm(text: str) -> str:
    words = re.sub(r"[^\wऀ-ॿ\s]", " ", text.lower()).split()
    while words and words[0] in _ARTICLES:
        words = words[1:]
    return " ".join(words)


class AnswerJudge:
    def __init__(self, model: StructuredModel, *, spend: Callable[[], bool] | None = None, timeout: float = 15.0) -> None:
        self._model = model
        self._spend = spend or (lambda: True)
        self._timeout = timeout

    async def judge(self, question: str, truth: str, reply: str) -> str:
        """match only for the right answer; anything doubtful, slow or malformed is not a match."""
        reply = " ".join(reply.split()[:MAX_REPLY_WORDS])
        if not reply:
            return NO_MATCH
        if _norm(reply) == _norm(truth):
            return MATCH  # an exact answer needs no model
        if not self._spend():
            return UNSURE
        message = f"Question: {question}\nThe true answer: {truth}\nWhat the person said: {reply}"
        try:
            raw = await asyncio.wait_for(
                self._model.structured(name="auth_judge", system=load_prompt("auth_judge.md"), user=message),
                timeout=self._timeout,
            )
        except Exception:
            return UNSURE
        verdict = raw.get("verdict") if isinstance(raw, dict) else None
        return verdict if verdict in (MATCH, NO_MATCH, UNSURE) else UNSURE
