"""The small interfaces the voice loop depends on, so engines can be swapped."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ..errors import OrchestratorError


class VoiceError(OrchestratorError):
    """A speech or microphone failure. The message is safe to show the user."""


@dataclass(frozen=True)
class Transcript:
    text: str
    # 0..1. Engines that cannot score a transcript report 1.0.
    confidence: float = 1.0
    # The captured audio, when the loop still has it: the speaker service
    # identifies from this. Transcripts from other sources carry b''.
    wav: bytes = b""


class Transcriber(Protocol):
    async def transcribe(self, wav: bytes) -> Transcript: ...


class Speaker(Protocol):
    async def say(self, text: str) -> None: ...


class Recorder(Protocol):
    auto_stop: bool

    def check(self) -> None:
        """Raise VoiceError if the microphone cannot be opened."""

    def start(self) -> None: ...

    def wait_done(self, timeout: float = 40.0) -> None:
        """Block until the user stops speaking (only used when ``auto_stop`` is true)."""

    def cancel(self) -> None:
        """Abort the recording in progress (``stop()`` then returns b'')."""

    def release(self) -> None:
        """Close the microphone (the conversation went idle)."""

    def stop(self) -> bytes:
        """Return the recording as WAV bytes, or b'' if there was no usable audio."""


@dataclass(frozen=True)
class Engines:
    transcriber: Transcriber
    speaker: Speaker
    label: str
