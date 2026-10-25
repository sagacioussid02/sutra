"""Small deterministic text helpers for recall and supersession."""

from __future__ import annotations

import re

_WORD = re.compile(r"[a-z0-9]+")

# Words that carry no retrieval signal. Kept short and obvious on purpose.
STOPWORDS = frozenset(
    """a about after all also am an and any are as at be been but by can could did do does
    for from had has have he her his how i if in into is it its just me my of
    on or our she so that the their them then there these they this to up us was we were
    what when where which who why will with would you your user""".split()
)


def tokens(text: str) -> list[str]:
    """Lowercased, apostrophe-free content words, in order, without duplicates."""
    words = _WORD.findall(text.lower().replace("'", "").replace("’", ""))
    seen: dict[str, None] = {}
    for word in words:
        if word not in STOPWORDS and len(word) >= 2:
            seen.setdefault(word, None)
    return list(seen)


def normalize(text: str) -> str:
    """Case, punctuation and whitespace insensitive form, for exact-duplicate checks."""
    return " ".join(_WORD.findall(text.lower().replace("'", "").replace("’", "")))


def overlap(a: str, b: str) -> float:
    """Overlap coefficient of the content words of two texts, in [0, 1].

    |A ∩ B| / min(|A|, |B|). Chosen over Jaccard because an updated fact
    ("paid on the 15th" → "paid on the 1st") usually adds or swaps one word and
    would score low on Jaccard. Needs at least two content words on each side,
    so a single shared word never counts as a match.
    """
    ta, tb = set(tokens(a)), set(tokens(b))
    if len(ta) < 2 or len(tb) < 2:
        return 0.0
    return len(ta & tb) / min(len(ta), len(tb))


def fts_query(text: str) -> str | None:
    """Build a safe FTS5 OR-query from free text, or None if it has no content words."""
    toks = tokens(text)
    if not toks:
        return None
    return " OR ".join(f'"{t}"' for t in toks)
