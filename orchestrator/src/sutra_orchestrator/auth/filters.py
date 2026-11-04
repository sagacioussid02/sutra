"""What may be asked about. Anything that could expose something private is never a source."""

from __future__ import annotations

import re

from ..personality import rules

MIN_WORDS, MAX_WORDS = 4, 30
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_NUMBERY = re.compile(r"\d[\d\s().-]{6,}\d")  # phone numbers and other long runs of digits
_MONEY = re.compile(r"[$€£¥]\s?\d|\b\d[\d,.]*\s?(?:dollars?|usd|eur|euros?|pounds?|rupees?|inr|k)\b", re.IGNORECASE)
_URL = re.compile(r"https?://|www\.|\b\w+\.(?:com|org|net|io)\b", re.IGNORECASE)
# Anything that mentions a secret is never a source, however long: it might contain the secret.
_SECRET = re.compile(
    r"\b(?:password|passcode|passphrase|pin|secret|token|api key|credential\w*|duress|authenticat\w*|verify)\b", re.IGNORECASE)
# Words aimed at Sutra's own controls; fine inside a longer account of an event, not as a short line.
_CONTROL = re.compile(r"\b(?:safe mode|limited mode|go quiet|stop listening|full mode|confirm|yes|no)\b", re.IGNORECASE)


# A turn is only a source if it is about the user: a first-person statement, not a question anyone could answer.
_PERSONAL = re.compile(r"\b(?:i|i'm|i've|i'd|i'll|im|my|me|mine|myself|we|we're|we've|our|us|let's)\b|मैं|मेरा|मेरी|मुझे|हम", re.IGNORECASE)


def usable(text: str, names: list[str], *, personal: bool = True) -> bool:
    """True if ``text`` is safe to keep as a source for a question.

    ``personal`` is for what the user said; reminders and plans are the user's by construction.
    """
    if personal and not _PERSONAL.search(text):
        return False
    words = text.split()
    if not MIN_WORDS <= len(words) <= MAX_WORDS:
        return False
    if rules.heavy(text) or rules.upset(text):
        return False
    if _EMAIL.search(text) or _NUMBERY.search(text) or _MONEY.search(text) or _URL.search(text):
        return False
    lowered = text.lower()
    if any(re.search(rf"(?<!\w){re.escape(n.lower())}(?!\w)", lowered) for n in names if n):
        return False  # other people are not ours to quiz about
    if _SECRET.search(text):
        return False
    if _CONTROL.search(text) and len(words) < 8:
        return False  # a short line aimed at the controls, not an event
    return True
