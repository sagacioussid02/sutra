"""The memory extractor: turns what the user said into durable statements.

The extractor is isolated by construction. Its input is built here from only
the user's own current message and (for resolving "yes, that one") their
previous message. It never receives tool results or any assistant text, so
injected text in a tool result has no path to a memory.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..prompts import load_prompt

KINDS = ("fact", "preference", "routine", "correction")
MAX_STATEMENTS = 3
_MIN_CHARS, _MAX_CHARS = 3, 300


@dataclass(frozen=True)
class Statement:
    content: str  # as the user would say it
    spoken: str  # second person, for the "Noted: ..." notice
    kind: str


def system_prompt() -> str:
    return load_prompt("extractor.md")


def build_user_message(utterance: str, previous: str | None) -> str:
    previous_text = previous.strip() if previous else "(none)"
    return (
        f"Their previous message (context only):\n{previous_text}\n\n"
        f"Their current message:\n{utterance.strip()}"
    )


def parse_statements(raw: Any) -> list[Statement]:
    """Validate the extractor's output. Anything malformed is dropped."""
    if not isinstance(raw, list):
        return []
    out: list[Statement] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        content, spoken, kind = item.get("content"), item.get("spoken"), item.get("kind")
        if not isinstance(content, str) or not isinstance(kind, str) or kind not in KINDS:
            continue
        content = " ".join(content.split())
        if not (_MIN_CHARS <= len(content) <= _MAX_CHARS):
            continue
        if not isinstance(spoken, str) or not spoken.strip() or len(spoken) > _MAX_CHARS:
            spoken = content
        out.append(Statement(content=content, spoken=" ".join(spoken.split()), kind=kind))
        if len(out) == MAX_STATEMENTS:
            break
    return out
