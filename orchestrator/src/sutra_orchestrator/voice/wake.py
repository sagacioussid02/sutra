"""Spotting "Hey Sutra" in a locally transcribed segment, allowing for how the name tends to be misheard."""

from __future__ import annotations

import difflib
import re
import unicodedata

_WORD = re.compile(r"[\wऀ-ॿ']+")
# Common mishearings of the name by a small speech model, in addition to a fuzzy match.
VARIANTS = {
    "sutra": {"sutra", "sootra", "suitra", "shutra", "sutras", "sutro", "sutraa", "sutter", "sootrah", "soutra", "सूत्र", "सुत्र"},
    "hey": {"hey", "hay", "hi", "hello", "ok", "okay", "yo", "ay"},
}
FUZZ = 0.78


def _similar(word: str, target: str) -> bool:
    if word in VARIANTS.get(target, ()):
        return True
    return difflib.SequenceMatcher(None, word, target).ratio() >= FUZZ


class WakeMatcher:
    """``match(text)`` returns what follows the wake phrase ("" if nothing does), or None if it was not said.

    The wake phrase must lead the utterance (after at most one filler word), so the name inside a longer sentence
    about something else does not wake it.
    """

    def __init__(self, phrases: tuple[str, ...] = ("hey sutra", "sutra")) -> None:
        self._phrases = [p.split() for p in (" ".join(x.lower().split()) for x in phrases) if p]

    def match(self, text: str) -> str | None:
        text = unicodedata.normalize("NFC", text)
        spans = [(m.group(0).lower().strip("'"), m.end()) for m in _WORD.finditer(text)]
        words = [w for w, _ in spans]
        for phrase in self._phrases:
            for start in (0, 1):
                end = start + len(phrase)
                if end > len(words):
                    continue
                if all(_similar(words[start + i], phrase[i]) for i in range(len(phrase))):
                    return text[spans[end - 1][1]:].lstrip(" ,.;:!?-—").strip()
        return None
