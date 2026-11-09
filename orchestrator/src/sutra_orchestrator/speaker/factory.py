"""Build the speaker service for the voice loop, from config.

Off by default: with ``SUTRA_SPEAKER`` off this returns None and the
voice loop attaches nothing, so turns carry no signal and the
orchestrator behaves exactly as before. On, the service identifies with
the shipped ``NullIdentifier`` (every voice unknown until a real local
embedding implementation is chosen and evaluated on the owner's voice),
classifies addressee with the model, and enrols through a local
owner-only store.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from ..config import Config
from ..model import IntentModel
from .addressee import AddresseeClassifier
from .enrolment import EnrolmentStore
from .identify import NullIdentifier
from .service import SpeakerService


def build_speaker(
    config: Config, model: IntentModel, resolve_dir: Callable[[str], Path]
) -> SpeakerService | None:
    if not config.speaker_enabled:
        return None
    return SpeakerService(
        identifier=NullIdentifier(),
        classifier=AddresseeClassifier(model, config.wake_words),
        enrolment=EnrolmentStore(resolve_dir(config.speaker_dir)),
        enabled=True,
        assistant_names=config.wake_words,
    )
