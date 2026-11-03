"""OpenAI speech-to-text and text-to-speech. Audio and reply text leave the machine."""

from __future__ import annotations

import asyncio
import math
from typing import Any

from .types import Transcript, VoiceError

DEFAULT_TTS_INSTRUCTIONS = (
    "Speak like a relaxed, warm person in the same room, in a natural conversational pace. Vary your "
    "pitch and rhythm the way people do: a little quicker on easy things, slower and softer when "
    "something is serious, with short natural pauses between thoughts. Smile when something is light. "
    "Do not sound like an announcer or a customer-service bot, and never read a list in a sing-song. "
    "Let small fillers like 'hmm' or 'okay' sound casual and unhurried."
)
CACHE_PHRASE_CHARS = 40  # short phrases (the fillers) are kept and replayed with no network round trip
CACHE_PHRASES = 24


def _client(api_key: str) -> Any:
    from openai import AsyncOpenAI

    return AsyncOpenAI(api_key=api_key)


def _confidence(logprobs: Any) -> float:
    """Geometric-mean token probability, or 1.0 when the API sent no scores."""
    values = [getattr(lp, "logprob", None) for lp in (logprobs or [])]
    values = [v for v in values if v is not None]
    if not values:
        return 1.0
    return max(0.0, min(1.0, math.exp(sum(values) / len(values))))


def _failure(what: str, exc: Exception) -> str:
    name = type(exc).__name__
    if name == "AuthenticationError":
        return (
            f"{what} failed: OpenAI rejected the API key. Check OPENAI_API_KEY in "
            "orchestrator/.env (no quotes or spaces, and a key that can use this model)."
        )
    if name == "PermissionDeniedError":
        return f"{what} failed: this OpenAI key is not allowed to use that model."
    if name == "RateLimitError":
        return f"{what} failed: OpenAI rate limit or quota reached."
    return f"{what} failed ({name})"


class OpenAITranscriber:
    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o-transcribe",
        *,
        prompt: str = "",
        language: str = "",
        client: Any | None = None,
    ) -> None:
        self._client = client or _client(api_key)
        self._model = model
        self._prompt = prompt
        self._language = language

    async def transcribe(self, wav: bytes) -> Transcript:
        kwargs: dict[str, Any] = {
            "model": self._model,
            "file": ("speech.wav", wav, "audio/wav"),
            "response_format": "json",
            "include": ["logprobs"],
        }
        if self._prompt:
            kwargs["prompt"] = self._prompt
        if self._language:
            kwargs["language"] = self._language
        try:
            resp = await self._client.audio.transcriptions.create(**kwargs)
        except Exception as exc:
            raise VoiceError(_failure("speech-to-text", exc)) from None
        text = (getattr(resp, "text", "") or "").strip()
        return Transcript(text, _confidence(getattr(resp, "logprobs", None)) if text else 0.0)


PCM_RATE = 24_000  # OpenAI "pcm" output: 24 kHz, signed 16-bit, mono


class OpenAISpeaker:
    """Streams speech so playback starts while the rest is still being generated."""

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o-mini-tts",
        voice: str = "coral",
        *,
        instructions: str = DEFAULT_TTS_INSTRUCTIONS,
        client: Any | None = None,
        play: Any | None = None,
    ) -> None:
        self._client = client or _client(api_key)
        self._model = model
        self._voice = voice
        self._instructions = instructions
        self._play = play or play_pcm_stream
        self._cache: dict[str, bytes] = {}

    async def say(self, text: str) -> None:
        if not text.strip():
            return
        cached = self._cache.get(text)
        if cached is not None:
            await self._play(_chunks(cached))
            return
        keep = len(text) <= CACHE_PHRASE_CHARS and len(self._cache) < CACHE_PHRASES
        heard: list[bytes] = []
        try:
            async with self._client.audio.speech.with_streaming_response.create(
                model=self._model,
                voice=self._voice,
                input=text,
                instructions=self._instructions,
                response_format="pcm",
            ) as resp:
                await self._play(_tee(resp.iter_bytes(4096), heard) if keep else resp.iter_bytes(4096))
        except VoiceError:
            raise
        except Exception as exc:
            raise VoiceError(_failure("text-to-speech", exc)) from None
        if keep and heard:
            self._cache[text] = b"".join(heard)  # only a phrase that played to the end is kept

    async def prewarm(self, phrases: Any) -> None:
        """Synthesize short phrases ahead of time so the first use is instant. Never raises."""
        for text in phrases:
            if text in self._cache or len(text) > CACHE_PHRASE_CHARS or len(self._cache) >= CACHE_PHRASES:
                continue
            try:
                async with self._client.audio.speech.with_streaming_response.create(
                    model=self._model, voice=self._voice, input=text,
                    instructions=self._instructions, response_format="pcm",
                ) as resp:
                    self._cache[text] = b"".join([c async for c in resp.iter_bytes(4096)])
            except Exception:
                return  # a missing or slow network is not worth a startup failure


async def _chunks(data: bytes) -> Any:
    for i in range(0, len(data), 4096):
        yield data[i : i + 4096]


async def _tee(chunks: Any, into: list[bytes]) -> Any:
    async for chunk in chunks:
        into.append(chunk)
        yield chunk


async def play_pcm_stream(chunks: Any) -> None:
    """Play 24 kHz 16-bit mono PCM chunks as they arrive."""
    import sounddevice as sd

    try:
        stream = sd.RawOutputStream(samplerate=PCM_RATE, channels=1, dtype="int16")
        stream.start()
    except Exception as exc:
        raise VoiceError(f"could not open the speakers ({exc})") from None
    leftover = b""
    cut = False
    try:
        async for chunk in chunks:
            data = leftover + chunk
            usable = len(data) // 2 * 2
            leftover = data[usable:]
            if usable:
                await asyncio.to_thread(stream.write, data[:usable])
    except asyncio.CancelledError:
        cut = True  # the user spoke over it: stop at once, do not play out what is queued
        raise
    finally:
        await asyncio.to_thread(stream.abort if cut else stream.stop)  # stop() lets queued audio finish
        stream.close()
