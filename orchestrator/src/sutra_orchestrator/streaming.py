"""Turning a model's text stream into sentences that can be spoken as they arrive.

A sentence is released only once the next one has begun, or the stream has ended without a tool call. A
single sentence of lead-in before a tool call is therefore never spoken. (If a model writes two or more
sentences before a tool call, all but the last are spoken; the voice client copes, see ``Streamed``.)
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable

log = logging.getLogger("sutra_orchestrator")

MIN_SENTENCE_CHARS = 24  # shorter ones ("Okay.", "Sure.") are joined to the next so speech is not choppy
_END = re.compile(r"""[.!?]+["')\]]*(?=\s)""")
_ABBREVIATIONS = frozenset(
    "dr mr mrs ms mx st vs etc e.g i.e a.m p.m u.s u.k no jr sr prof inc ltd approx min max".split()
)


def _is_abbreviation(before: str) -> bool:
    word = before.rsplit(None, 1)[-1].lower().lstrip("\"'([") if before.strip() else ""
    return word.rstrip(".") in _ABBREVIATIONS or word.rstrip(".") in {a.replace(".", "") for a in _ABBREVIATIONS}


class SentenceSplitter:
    """Feed it text deltas; it returns complete sentences. ``flush`` returns what is left."""

    def __init__(self) -> None:
        self._buf = ""
        self._carry = ""  # a short sentence waiting to be joined to the next

    def feed(self, delta: str) -> list[str]:
        self._buf += delta
        out: list[str] = []
        while True:
            cut = self._next_cut()
            if cut is None:
                return out
            sentence, self._buf = self._buf[:cut].strip(), self._buf[cut:].lstrip()
            if not sentence:
                continue
            sentence = f"{self._carry} {sentence}".strip()
            self._carry = ""
            if len(sentence) < MIN_SENTENCE_CHARS:
                self._carry = sentence
            else:
                out.append(sentence)

    def _next_cut(self) -> int | None:
        for m in _END.finditer(self._buf):
            if not _is_abbreviation(self._buf[: m.start()]):
                return m.end()
        return None

    def has_pending(self) -> bool:
        """True once text of a not-yet-finished sentence has begun to arrive."""
        return bool(self._buf.strip())

    def flush(self) -> str:
        rest = f"{self._carry} {self._buf}".strip()
        self._buf = self._carry = ""
        return rest


class Streamer:
    """One model call's text, delivered to ``emit`` a sentence at a time, one sentence behind."""

    def __init__(self, emit: Callable[[str], None]) -> None:
        self._emit = emit
        self._split = SentenceSplitter()
        self._held: str | None = None
        self.released: list[str] = []

    def _release(self, sentence: str) -> None:
        self.released.append(sentence)
        try:
            self._emit(sentence)
        except Exception:  # a listener that fails must never break the turn
            log.debug("a stream listener failed", exc_info=True)

    def feed(self, delta: str) -> None:
        for sentence in self._split.feed(delta):
            if self._held is not None:
                self._release(self._held)
            self._held = sentence
        if self._held is not None and self._split.has_pending():
            self._release(self._held)  # the next sentence has begun: this one is safe to say
            self._held = None

    def finish(self, stop_reason: str | None) -> None:
        """End of the model's output. After a tool call nothing is left to say, so held text is dropped."""
        tail = self._split.flush()
        if stop_reason == "tool_use":
            self._held = None
            return
        if self._held is not None and tail and len(tail) < MIN_SENTENCE_CHARS:
            self._held, tail = f"{self._held} {tail}", ""
        if self._held is not None:
            self._release(self._held)
        if tail:
            self._release(tail)
        self._held = None
