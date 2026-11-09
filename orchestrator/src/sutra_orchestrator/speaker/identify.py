"""Speaker identification behind the signal interface.

The interface is the stable seam: the voice pipeline calls
``identify(wav)`` on the captured utterance and attaches the returned
signal. Which implementation fills it is an open question in the change
design, deliberately left to a measured choice: a local embedding model
or the transcription provider's speaker features, decided on latency and
accuracy with the owner's voice, on a real setup.

Until that choice is made and evaluated, the shipped implementation is
``NullIdentifier``: it always returns ``unknown``, adds no dependency,
sends nothing anywhere, and can never misidentify anyone. That is the
safe default — an unidentified voice degrades to today's posture
(push-to-talk or an explicit open, confirm-first as before) rather than
to a guessed identity. A real identifier drops in behind this same
interface; the signal, the addressee decision, and the confirmation
binding do not change.
"""

from __future__ import annotations

from typing import Protocol

from .signal import SpeakerSignal


class SpeakerIdentifier(Protocol):
    """Identify the speaker of one captured utterance.

    Implementations are local-first and synchronous: they run on audio the
    pipeline already captured for transcription, in parallel with it, and
    must not add a network dependency beyond the one they declare. They
    return ``SpeakerSignal.unknown()`` for any voice with no enrolment
    profile — never a guess.
    """

    def identify(self, wav: bytes) -> SpeakerSignal:
        """Return the speaker signal for ``wav`` (WAV bytes, or b'' if none)."""
        ...


class NullIdentifier:
    """No identification implementation yet: every voice is unknown.

    This is what ships until a local embedding implementation is chosen
    and evaluated on the owner's voice. It keeps the feature safe to turn
    on: the addressee classifier still works from text and conversation
    state, and confirmations keep the posture they had before this
    change, because an unknown signal can only confirm a claim that no
    identified speaker requested.
    """

    def identify(self, wav: bytes) -> SpeakerSignal:
        return SpeakerSignal.unknown()
