"""The speaker service: one handle the voice loop holds.

It composes the pieces of this change — identification, enrolment, and
addressee classification — and owns the conversation state the addressee
decision needs (open or not, who opened it, whether this is the first
turn after opening). The orchestrator never sees this service: it
receives the per-turn signal and verdict, and applies its own gate.

When the feature is off, every method degrades to today's behaviour:
identification returns unknown, classification returns no verdict (the
caller passes nothing and the orchestrator uses its existing
``addressed_to_assistant`` flag), and no enrolment is consulted.
"""

from __future__ import annotations

from .addressee import Addressee, AddresseeClassifier, ConversationState
from .enrolment import EnrolmentStore
from .identify import NullIdentifier, SpeakerIdentifier
from .signal import SpeakerSignal


class SpeakerService:
    """Identification + addressee classification for the voice loop."""

    def __init__(
        self,
        *,
        identifier: SpeakerIdentifier | None = None,
        classifier: AddresseeClassifier | None = None,
        enrolment: EnrolmentStore | None = None,
        enabled: bool = False,
        assistant_names: tuple[str, ...] = ("sutra",),
    ) -> None:
        self._identifier = identifier if identifier is not None else NullIdentifier()
        self._classifier = classifier
        self._enrolment = enrolment
        self._enabled = enabled
        self._assistant_names = tuple(assistant_names)
        self._state = ConversationState()

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def enrolment(self) -> EnrolmentStore | None:
        """The enrolment store, for the control surface. None when not configured."""
        return self._enrolment

    @property
    def conversation_state(self) -> ConversationState:
        return self._state

    def identify(self, wav: bytes) -> SpeakerSignal:
        """The speaker signal for one captured utterance.

        With the feature off, or with no audio, this is unknown — the
        caller must not treat the absence of a signal as an identity.
        """
        if not self._enabled or not wav:
            return SpeakerSignal.unknown()
        return self._identifier.identify(wav)

    def note_conversation_opened(self, opened_by: str | None = None) -> None:
        """A conversation just opened (name spoken, wake phrase, or first turn).

        The first turn after opening is addressed by construction.
        """
        self._state = ConversationState(open=True, opened_by=opened_by, just_opened=True)

    def note_conversation_closed(self) -> None:
        """The conversation ended (inactivity, explicit close, or switched off)."""
        self._state = ConversationState()

    async def classify_utterance(
        self, text: str, signal: SpeakerSignal, *, push_to_talk: bool = False
    ) -> Addressee | None:
        """The addressee verdict for one utterance, or None when the feature is off.

        The state advances after the first turn: only the turn that opened
        the conversation counts as just opened.
        """
        if not self._enabled:
            return None
        state = ConversationState(
            open=self._state.open,
            opened_by=self._state.opened_by,
            just_opened=self._state.just_opened,
            push_to_talk=push_to_talk,
        )
        self._state.just_opened = False
        if self._classifier is None:
            # No model wired: the deterministic pre-filter still decides the
            # clear cases; anything else is unclear, never addressed.
            from .addressee import prefilter

            verdict = prefilter(text, state, self._assistant_names)
            return verdict if verdict is not None else Addressee.UNCLEAR
        return await self._classifier.classify(text, signal, state)
