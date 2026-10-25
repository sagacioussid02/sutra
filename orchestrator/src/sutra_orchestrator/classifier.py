"""Intent classification for replies to a pending confirmation.

Two stages. A fast path in code resolves unambiguous replies ("yes", "cancel")
with no model call. Anything else goes to an isolated classifier call whose
only inputs are the gateway's pending description and the user's reply. It
never sees conversation history or tool results, so text injected through a
tool result has no path to the consent decision.
"""

from __future__ import annotations

import asyncio
import logging
import re

from .model import IntentModel
from .prompts import load_prompt

log = logging.getLogger("sutra_orchestrator")

AFFIRM = "affirm"
DENY = "deny"
MODIFY = "modify"
UNCLEAR = "unclear"
LABELS = (AFFIRM, DENY, MODIFY, UNCLEAR)

# Whole-utterance matches only, after normalization. Deliberately short: a
# phrase belongs here only if it can never mean anything but yes or no.
AFFIRMATIVES = frozenset(
    {
        "yes",
        "yeah",
        "yep",
        "yup",
        "confirm",
        "confirmed",
        "affirmative",
        "go ahead",
        "do it",
        "please do",
        "yes please",
        "yes do it",
        "yes go ahead",
    }
)
NEGATIVES = frozenset(
    {
        "no",
        "nope",
        "nah",
        "cancel",
        "stop",
        "abort",
        "negative",
        "never mind",
        "nevermind",
        "dont",
        "no thanks",
        "no thank you",
        "cancel that",
        "dont do it",
    }
)

_NON_WORD = re.compile(r"[^a-z0-9\s]")
_SPACES = re.compile(r"\s+")


def normalize(text: str) -> str:
    text = text.lower().replace("'", "").replace("’", "")
    text = _NON_WORD.sub(" ", text)
    return _SPACES.sub(" ", text).strip()


def fast_path(text: str) -> str | None:
    """Return affirm/deny for an unambiguous whole-utterance match, else None."""
    norm = normalize(text)
    if norm in AFFIRMATIVES:
        return AFFIRM
    if norm in NEGATIVES:
        return DENY
    return None


class IntentClassifier:
    def __init__(self, model: IntentModel, timeout: float = 8.0) -> None:
        self._model = model
        self._timeout = timeout
        self._system = load_prompt("classifier.md")

    async def classify(self, description: str, reply: str) -> str:
        """Label ``reply``. Any failure is treated as ``unclear``, never ``affirm``."""
        fast = fast_path(reply)
        if fast is not None:
            return fast
        user = f"Action awaiting confirmation (system-supplied data):\n{description}\n\nUser's reply:\n{reply}"
        try:
            label = await asyncio.wait_for(
                self._model.classify(system=self._system, user=user), timeout=self._timeout
            )
        except Exception as exc:  # includes timeouts and API errors
            log.warning("intent classifier failed (%s); treating as unclear", type(exc).__name__)
            return UNCLEAR
        label = label.strip().lower() if isinstance(label, str) else ""
        if label not in LABELS:
            log.warning("intent classifier returned an invalid label; treating as unclear")
            return UNCLEAR
        return label
