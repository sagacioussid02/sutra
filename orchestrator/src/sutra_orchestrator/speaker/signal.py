"""The speaker signal: what the voice pipeline knows about who just spoke.

One value per utterance: either an enrolled speaker id with a confidence
and the method that produced it, or ``unknown``. ``unknown`` is a complete
answer — the pipeline never guesses an identity for an unenrolled voice.

The orchestrator consumes the signal; it never trusts a client-asserted
label. See ``identify.py`` for how a signal is produced and
``addressee.py`` for how it feeds the addressee decision.
"""

from __future__ import annotations

from dataclasses import dataclass

METHOD_NONE = "none"
"""Method recorded when no identification was attempted or possible."""


@dataclass(frozen=True)
class SpeakerSignal:
    """Who spoke, how sure the pipeline is, and how it decided.

    ``speaker_id`` is the enrolled speaker's id, or ``None`` for unknown.
    ``confidence`` is 0..1; an unknown speaker always carries 0.0.
    ``method`` names the identification implementation (for example
    ``"enrolled-voiceprint"``); ``"none"`` when unknown.
    """

    speaker_id: str | None = None
    confidence: float = 0.0
    method: str = METHOD_NONE

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"speaker confidence must be 0..1, got {self.confidence!r}")
        if self.speaker_id is None and self.confidence != 0.0:
            raise ValueError("an unknown speaker carries no confidence")
        if self.speaker_id is not None and not self.speaker_id.strip():
            raise ValueError("an enrolled speaker id must not be blank")

    @property
    def is_known(self) -> bool:
        """True when the pipeline identified an enrolled speaker."""
        return self.speaker_id is not None

    @classmethod
    def unknown(cls) -> "SpeakerSignal":
        """The signal for a voice with no enrolment profile."""
        return cls(speaker_id=None, confidence=0.0, method=METHOD_NONE)

    @classmethod
    def identified(cls, speaker_id: str, confidence: float, method: str) -> "SpeakerSignal":
        """The signal for an enrolled speaker, at the measured confidence."""
        return cls(speaker_id=speaker_id, confidence=confidence, method=method)
