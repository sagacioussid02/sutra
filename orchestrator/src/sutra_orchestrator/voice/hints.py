"""Words to give the speech recognizer, so names it has never seen are not mangled ("Orem" -> "Zoram").

Two sources: ``SUTRA_STT_HINTS`` (names you list) and proper nouns found in what the user told Sutra to
remember. Only the hint text goes to the recognizer, and only in cloud mode; nothing else from memory does.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

MAX_NAMES = 25
_CAPITALIZED = re.compile(r"\b[A-Z][a-z]{2,}(?:\s+[A-Z][a-z]{2,})?\b")
# Capitalized words that are not names.
_COMMON = frozenset(
    """the and but for you your have has had not this that with from they them their what when where which
    who why how monday tuesday wednesday thursday friday saturday sunday january february march april may june
    july august september october november december user sutra""".split()
)


def memory_names(contents: Iterable[str]) -> list[str]:
    """Proper-noun-looking words from remembered statements, most recent first, without repeats."""
    seen: dict[str, None] = {}
    for content in contents:
        for match in _CAPITALIZED.finditer(content):
            # A capitalized first word of a sentence is just a capital; skip it unless it recurs mid-sentence.
            if match.start() == 0 or content[max(0, match.start() - 2) : match.start()].strip() in (".", "!", "?", ""):
                continue
            name = match.group(0)
            if name.lower() not in _COMMON and name.split()[0].lower() not in _COMMON:
                seen.setdefault(name, None)
    return list(seen)[:MAX_NAMES]


def build_hint(assistant_name: str, extra: Iterable[str], remembered: Iterable[str]) -> str:
    names = list(dict.fromkeys([assistant_name, "Sutra", "minions", "finanxe", "twin", *extra, *remembered]))
    return "Names you may hear: " + ", ".join(names) + "."
