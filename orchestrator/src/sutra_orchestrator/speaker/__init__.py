"""Speaker identification and addressee detection for voice turns.

The voice pipeline attaches a ``SpeakerSignal`` to each utterance and
classifies whether it is addressed to the assistant; the orchestrator
consumes both. Enrolment is explicit, local, and revocable.
"""

from .addressee import Addressee, AddresseeClassifier, ConversationState, TurnGate, prefilter
from .enrolment import EnrolmentStore, SpeakerProfile
from .factory import build_speaker
from .identify import NullIdentifier, SpeakerIdentifier
from .service import SpeakerService
from .signal import METHOD_NONE, SpeakerSignal

__all__ = [
    "Addressee",
    "AddresseeClassifier",
    "ConversationState",
    "EnrolmentStore",
    "METHOD_NONE",
    "NullIdentifier",
    "SpeakerIdentifier",
    "SpeakerProfile",
    "SpeakerService",
    "SpeakerSignal",
    "TurnGate",
    "build_speaker",
    "prefilter",
]
