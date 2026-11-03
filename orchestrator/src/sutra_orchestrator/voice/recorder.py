"""Microphone capture with sounddevice."""

from __future__ import annotations

import array
import collections
import io
import math
import threading
import wave

from .types import VoiceError

SAMPLE_RATE = 16_000
MIN_SECONDS = 0.3
BLOCK_MS = 30
MIN_SPEECH_RMS = 250.0


def pcm_to_wav(pcm: bytes, sample_rate: int = SAMPLE_RATE) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(pcm)
    return buf.getvalue()


def block_rms(block: bytes) -> float:
    samples = array.array("h")
    samples.frombytes(block[: len(block) // 2 * 2])
    if not samples:
        return 0.0
    return math.sqrt(sum(x * x for x in samples) / len(samples))


class EndpointDetector:
    """Decides when the user has finished speaking, from per-block loudness.

    It learns the room's noise floor from the first blocks, treats a few loud blocks
    in a row as speech, and calls the utterance finished after ``silence_ms`` of quiet.
    If nothing is said within ``no_speech_ms`` it gives up, and ``max_ms`` caps a turn.
    """

    CALIBRATION_BLOCKS = 6
    SPEECH_BLOCKS = 3
    # A block this loud is speech even before the noise floor is learned, so talking
    # right away is not mistaken for background noise.
    OBVIOUS_SPEECH_RMS = 1500.0

    def __init__(
        self,
        *,
        silence_ms: int = 1200,
        no_speech_ms: int = 6000,
        max_ms: int = 30_000,
        block_ms: int = BLOCK_MS,
    ) -> None:
        self._silence = silence_ms
        self._no_speech = no_speech_ms
        self._max = max_ms
        self._block = block_ms
        self._floor: list[float] = []
        self._threshold = MIN_SPEECH_RMS
        self._loud_run = 0
        self.speech_started = False
        self._quiet_ms = 0
        self._elapsed = 0

    def feed(self, rms: float) -> bool:
        """Feed one block's loudness. Returns True when the utterance is over."""
        self._elapsed += self._block
        calibrating = len(self._floor) < self.CALIBRATION_BLOCKS
        if calibrating and rms < self.OBVIOUS_SPEECH_RMS:
            self._floor.append(rms)
            if len(self._floor) == self.CALIBRATION_BLOCKS:
                floor = sorted(self._floor)[len(self._floor) // 2]
                self._threshold = max(MIN_SPEECH_RMS, floor * 2.5)
            self._loud_run = 0
            return False
        loud = rms >= self._threshold
        if not self.speech_started:
            self._loud_run = self._loud_run + 1 if loud else 0
            if self._loud_run >= self.SPEECH_BLOCKS:
                self.speech_started = True
                self._quiet_ms = 0
            return self._elapsed >= self._no_speech
        self._quiet_ms = 0 if loud else self._quiet_ms + self._block
        return self._quiet_ms >= self._silence or self._elapsed >= self._max


class MicRecorder:
    """Records from the microphone. With ``auto_stop`` it ends when the user stops talking.

    The input stream stays open between the turns of one conversation, so listening
    starts instantly after a reply, and the last ~150ms before ``start()`` are kept so the
    first word is not clipped. Call ``release()`` when the conversation ends: nothing is
    captured while idle.
    """

    PREROLL_BLOCKS = 5

    def __init__(
        self,
        sample_rate: int = SAMPLE_RATE,
        *,
        auto_stop: bool = True,
        silence_ms: int = 1200,
        no_speech_ms: int = 6000,
    ) -> None:
        self._rate = sample_rate
        self.auto_stop = auto_stop
        self._silence_ms = silence_ms
        self._no_speech_ms = no_speech_ms
        self._lock = threading.Lock()
        self._chunks: list[bytes] = []
        self._preroll: collections.deque[bytes] = collections.deque(maxlen=self.PREROLL_BLOCKS)
        self._listening = False
        self._stream = None
        self._detector: EndpointDetector | None = None
        self._done = threading.Event()
        self._cancelled = False
        self.heard_speech = False

    def _callback(self, indata, frames, time_info, status):  # noqa: ARG002
        block = bytes(indata)
        with self._lock:
            if not self._listening:
                self._preroll.append(block)
                return
            self._chunks.append(block)
            det = self._detector
        if det is not None and det.feed(block_rms(block)):
            self._done.set()

    def _open(self):
        import sounddevice as sd

        try:
            return sd.RawInputStream(
                samplerate=self._rate,
                channels=1,
                dtype="int16",
                blocksize=self._rate * BLOCK_MS // 1000,
                callback=self._callback,
            )
        except Exception as exc:  # PortAudioError and friends
            raise VoiceError(
                f"could not open the microphone ({exc}). On macOS, allow microphone "
                "access for your terminal in System Settings > Privacy & Security."
            ) from None

    def check(self) -> None:
        stream = self._open()
        stream.close()

    def start(self) -> None:
        if self._stream is None:
            self._stream = self._open()
            self._stream.start()
        self._done.clear()
        self._cancelled = False
        self.heard_speech = False
        self._detector = (
            EndpointDetector(silence_ms=self._silence_ms, no_speech_ms=self._no_speech_ms)
            if self.auto_stop
            else None
        )
        with self._lock:
            self._chunks = list(self._preroll)
            self._listening = True

    def wait_done(self, timeout: float = 40.0) -> None:
        """Block until the user has finished speaking (auto_stop mode only)."""
        self._done.wait(timeout)

    def cancel(self) -> None:
        """Abort the recording in progress; ``stop()`` will then return nothing."""
        self._cancelled = True
        self._done.set()

    def release(self) -> None:
        """Close the microphone. Called when the conversation goes idle."""
        stream, self._stream = self._stream, None
        with self._lock:
            self._listening = False
            self._preroll.clear()
        if stream is not None:
            stream.stop()
            stream.close()

    def stop(self) -> bytes:
        with self._lock:
            self._listening = False
            pcm = b"".join(self._chunks)
            self._chunks = []
        det, self._detector = self._detector, None
        self.heard_speech = bool(det and det.speech_started)
        if self._cancelled:
            return b""
        if not self.auto_stop:
            self.release()  # press-Enter mode never keeps the mic open between turns
        if det is not None and not det.speech_started:
            return b""
        if len(pcm) < int(self._rate * 2 * MIN_SECONDS):
            return b""
        if not any(pcm):
            raise VoiceError(
                "the microphone returned pure silence. If this keeps happening, allow "
                "microphone access for your terminal in System Settings > Privacy & Security."
            )
        return pcm_to_wav(pcm, self._rate)
