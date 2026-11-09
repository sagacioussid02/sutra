"""Addressee detection: is this utterance Sutra's business?

In an open conversation every utterance is classified as addressed to the
assistant, addressed elsewhere, or unclear, from the utterance, the
speaker signal, and the conversation state — never from a tool. The
turn gate is asymmetric on purpose:

- Would act (tools, confirmations, writes): requires *addressed*.
  Unclear is not enough.
- Would only answer: *addressed* or *unclear* may proceed.
- *Elsewhere* never proceeds: no tools, offers, or replies.

A deterministic pre-filter runs first so the common cases cost no model
call: push-to-talk counts as addressed, the turn that just opened a
conversation is addressed, and with no conversation open nothing is
addressed until the assistant's name is spoken. Anything the pre-filter
cannot decide goes to a small tools-off classifier on the same pattern
as the confirmation classifier: an isolated call whose only inputs are
the utterance, the speaker signal, and the conversation state. A
classifier failure is *unclear* — the turn may be answered, never acted
on.
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from enum import StrEnum

from ..model import IntentModel
from ..prompts import load_prompt
from .signal import SpeakerSignal

log = logging.getLogger("sutra_orchestrator")


class Addressee(StrEnum):
    """What the addressee classifier decided about one utterance."""

    ADDRESSED = "addressed"
    ELSEWHERE = "elsewhere"
    UNCLEAR = "unclear"


LABELS = (Addressee.ADDRESSED.value, Addressee.ELSEWHERE.value, Addressee.UNCLEAR.value)


@dataclass
class ConversationState:
    """What the voice loop knows about the conversation this turn is in.

    ``open`` is True while a conversation is running (it was opened by
    the assistant's name, a wake phrase, or push-to-talk). ``opened_by``
    is the enrolled speaker who opened it, or None. ``just_opened`` is
    True for the first turn after opening — that turn is addressed by
    construction, since opening is itself addressing the assistant.
    ``push_to_talk`` is True for a turn the user started deliberately
    (an Enter press), which also counts as addressed.
    """

    open: bool = False
    opened_by: str | None = None
    just_opened: bool = False
    push_to_talk: bool = False


_NAME_SPLIT = re.compile(r"[^a-z0-9]+")


def _mentions_name(text: str, assistant_names: tuple[str, ...]) -> bool:
    words = set(_NAME_SPLIT.split(text.lower()))
    for name in assistant_names:
        parts = [p for p in _NAME_SPLIT.split(name.lower()) if p]
        if parts and all(p in words for p in parts):
            return True
    return False


def prefilter(
    text: str, state: ConversationState, assistant_names: tuple[str, ...]
) -> Addressee | None:
    """Decide without a model call, or return None when one is needed.

    Push-to-talk and the turn that just opened a conversation are
    addressed. With no conversation open, only the assistant's name
    opens one — anything else is elsewhere. A name spoken mid-conversation
    is addressed too. Everything else needs the classifier.
    """
    if state.push_to_talk or state.just_opened:
        return Addressee.ADDRESSED
    if _mentions_name(text, assistant_names):
        return Addressee.ADDRESSED
    if not state.open:
        return Addressee.ELSEWHERE
    return None


class AddresseeClassifier:
    """The tools-off addressee classifier: pre-filter, then one isolated model call.

    ``model`` may be None (for example in tests, or when no model is
    configured): every undecided utterance is then *unclear*, which is
    safe — it may be answered, never acted on.
    """

    def __init__(
        self,
        model: IntentModel | None,
        assistant_names: tuple[str, ...] = ("sutra",),
        timeout: float = 8.0,
    ) -> None:
        self._model = model
        self._assistant_names = tuple(n.lower() for n in assistant_names)
        self._timeout = timeout
        self._system = load_prompt("addressee.md")

    async def classify(
        self, text: str, signal: SpeakerSignal, state: ConversationState
    ) -> Addressee:
        """Label one utterance. Any failure is *unclear*, never *addressed*."""
        fast = prefilter(text, state, self._assistant_names)
        if fast is not None:
            return fast
        if self._model is None:
            return Addressee.UNCLEAR
        speaker = signal.speaker_id if signal.is_known else "unknown"
        opened_by = state.opened_by if state.opened_by is not None else "unknown"
        user = (
            "Conversation: open, opened by "
            f"{opened_by}.\n"
            f"Speaker: {speaker}.\n"
            "Assistant's name: "
            + ", ".join(self._assistant_names)
            + ".\n\nUser's reply:\n"
            + text
        )
        try:
            label = await asyncio.wait_for(
                self._model.classify(system=self._system, user=user), timeout=self._timeout
            )
        except Exception as exc:  # includes timeouts and API errors
            log.warning("addressee classifier failed (%s); treating as unclear", type(exc).__name__)
            return Addressee.UNCLEAR
        label = label.strip().lower() if isinstance(label, str) else ""
        if label not in LABELS:
            log.warning("addressee classifier returned an invalid label; treating as unclear")
            return Addressee.UNCLEAR
        return Addressee(label)


class TurnGate:
    """The asymmetric rule, as a pure function of the verdict.

    ``decide`` returns "proceed" (act and answer), "answer_only"
    (answer without tools, offers, or confirmations), or "ignore"
    (nothing at all — no reply, no tools, no history).
    """

    @staticmethod
    def decide(addressee: Addressee) -> str:
        if addressee is Addressee.ELSEWHERE:
            return "ignore"
        if addressee is Addressee.UNCLEAR:
            return "answer_only"
        return "proceed"
