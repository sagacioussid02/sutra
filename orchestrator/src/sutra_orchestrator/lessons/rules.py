"""What a lesson may say and be, decided in code. The model's output is checked here, never trusted.

A lesson has exactly two possible effects: ``guidance`` (a line in a labelled prompt block) and
``block`` (a stop on a kind or topic of offer). There is no field in which it could name a tool, a
file, a setting or a permission, so model output that tries is simply not representable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

TEXT_MIN, TEXT_MAX = 8, 160
EFFECTS = ("guidance", "block")
BLOCK_KINDS = ("followup", "timely")

# A tripwire, not the safety argument: the confirmation gate lives in code and never consults
# lessons. This only keeps a lesson that reads like an attempt to weaken it from reaching the user.
_FORBIDDEN = re.compile(
    r"\b(confirm\w*|approv\w*|authori[sz]\w*|permission\w*|password\w*|token\w*|api[- ]?key\w*|"
    r"secret\w*|credential\w*|system prompt|instruction\w*|ignor\w*|overrid\w*|bypass\w*|disabl\w*|"
    r"without (?:asking|checking|telling)|don'?t ask|never ask|stop asking|no need to ask|skip|"
    r"tool\w*|setting\w*|config\w*|prompt\w*|gateway|env(?:ironment)? var\w*|\w+_\w+)\b",
    re.IGNORECASE,
)
_SENTENCE_END = re.compile(r"[.!?]+(?:\s+\S|$)")


@dataclass(frozen=True)
class Proposal:
    text: str
    effect: str = "guidance"
    kind: str = ""
    topic: str = ""


def clean_text(value: Any) -> str | None:
    """One tidy sentence of 8 to 160 characters, or None."""
    if not isinstance(value, str):
        return None
    text = " ".join(value.split()).strip()
    if not TEXT_MIN <= len(text) <= TEXT_MAX:
        return None
    body = text.rstrip(".!?")
    if _SENTENCE_END.search(body + " x") and re.search(r"[.!?]\s+\S", body):
        return None  # more than one sentence
    return text


def tripwire(text: str) -> str | None:
    """The word that made a guidance lesson unacceptable, or None."""
    match = _FORBIDDEN.search(text)
    return match.group(0).lower() if match else None


def guidance(raw: Any) -> Proposal | None:
    """A guidance proposal from model output, or None if it is not acceptable."""
    text = clean_text(raw)
    if text is None or tripwire(text) is not None:
        return None
    return Proposal(text)
