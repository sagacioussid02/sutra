"""Local engines: nothing here sends audio or reply text off the machine."""

from __future__ import annotations

import asyncio
import io
import math
import wave

from ..i18n import DEVANAGARI
from .types import Transcript, VoiceError


class SaySpeaker:
    """macOS ``say``. Text goes over stdin, never as an argument."""

    def __init__(self, voice: str = "", hindi_voice: str = "Lekha") -> None:
        self._voice = voice
        self._hindi_voice = hindi_voice

    async def say(self, text: str) -> None:
        if not text.strip():
            return
        voice = self._hindi_voice if self._hindi_voice and DEVANAGARI.search(text) else self._voice
        args = ["say"] + (["-v", voice] if voice else [])
        try:
            proc = await asyncio.create_subprocess_exec(*args, stdin=asyncio.subprocess.PIPE)
        except FileNotFoundError:
            raise VoiceError("the say command was not found; local speech needs macOS") from None
        try:
            await proc.communicate(text.encode("utf-8"))
        except asyncio.CancelledError:
            proc.terminate()  # interrupted: stop talking now
            raise


def _wav_to_float32(wav: bytes):
    import numpy as np

    with wave.open(io.BytesIO(wav), "rb") as w:
        frames = w.readframes(w.getnframes())
    return np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0


class FasterWhisperTranscriber:
    def __init__(self, model_size: str = "base.en", language: str | None = None) -> None:
        self._size = model_size
        self._language = language or None  # None: detect it (needs a multilingual model, not base.en)
        self._model = None

    def _load(self):
        if self._model is None:
            try:
                from faster_whisper import WhisperModel
            except ImportError:
                raise VoiceError(
                    "local speech-to-text needs faster-whisper: "
                    'uv pip install -e ".[voice-local]"'
                ) from None
            self._model = WhisperModel(self._size, compute_type="int8")
        return self._model

    def _run(self, wav: bytes) -> Transcript:
        segments, _info = self._load().transcribe(_wav_to_float32(wav), beam_size=1, language=self._language)
        segs = list(segments)
        text = " ".join(s.text.strip() for s in segs).strip()
        if not text:
            return Transcript("", 0.0)
        mean_lp = sum(s.avg_logprob for s in segs) / len(segs)
        speech = 1.0 - max(s.no_speech_prob for s in segs)
        return Transcript(text, max(0.0, min(1.0, math.exp(mean_lp) * speech)))

    async def transcribe(self, wav: bytes) -> Transcript:
        return await asyncio.to_thread(self._run, wav)
