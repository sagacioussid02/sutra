"""Interrupting Sutra while it speaks, speech-recognition vocabulary hints, headphone detection."""

from __future__ import annotations

import asyncio

import pytest

from sutra_orchestrator.errors import ConfigError
from sutra_orchestrator.voice.config import load_voice_config
from sutra_orchestrator.voice.devices import looks_like_headphones
from sutra_orchestrator.voice.hints import build_hint, memory_names
from sutra_orchestrator.voice.local_engines import SaySpeaker
from sutra_orchestrator.voice.loop import VoiceSession, VoiceSettings
from sutra_orchestrator.voice.recorder import EndpointDetector
from sutra_orchestrator.voice.types import Engines, Transcript

# ----------------------------------------------------------------- hints


def test_names_the_user_has_told_sutra_become_recognizer_hints():
    got = memory_names(["I live in Orem, Utah", "My wife Priya works at Intel.", "Paid on the 15th", "Sam is my dentist"])
    assert got == ["Orem", "Utah", "Priya", "Intel"]  # sentence-initial words are just capitals
    assert "Monday" not in memory_names(["I go to the gym every Monday"])
    hint = build_hint("Sutra", ["Provo"], ["Orem"])
    assert hint == "Names you may hear: Sutra, minions, finanxe, twin, Provo, Orem."
    assert len(memory_names([f"I met Person{'x' * i} today" for i in range(40)])) <= 25


def test_config_for_hints_and_interrupting():
    cfg = load_voice_config({}, dotenv_path=None)
    assert cfg.stt_hints == () and cfg.barge_in == "auto"
    cfg = load_voice_config({"SUTRA_STT_HINTS": " Orem, Provo ,", "SUTRA_BARGE_IN": "yes"}, dotenv_path=None)
    assert cfg.stt_hints == ("Orem", "Provo") and cfg.barge_in == "on"
    assert load_voice_config({"SUTRA_BARGE_IN": "off"}, dotenv_path=None).barge_in == "off"
    with pytest.raises(ConfigError):
        load_voice_config({"SUTRA_BARGE_IN": "sometimes"}, dotenv_path=None)


@pytest.mark.parametrize(
    "name,expected",
    [
        ("External Headphones", True),
        ("AirPods Pro", True),
        ("MacBook Pro Speakers", False),
        ("LG Display Audio", False),
        ("Jabra Speak 510 USB", False),  # a speakerphone is speakers
    ],
)
def test_headphones_are_detected_by_name_and_speakers_are_not(name, expected):
    assert looks_like_headphones(name) is expected


# ------------------------------------------------------------- the detector


def run_detector(det, blocks):
    return [det.feed(rms) for rms in blocks]


def test_interrupting_needs_a_longer_burst_than_ordinary_speech():
    quiet, loud = 100.0, 4000.0
    calm = [quiet] * 6
    ordinary = EndpointDetector()
    run_detector(ordinary, calm + [loud] * 3)
    assert ordinary.speech_started  # three loud blocks start an ordinary utterance
    careful = EndpointDetector(speech_blocks=EndpointDetector.BARGE_IN_SPEECH_BLOCKS)
    run_detector(careful, calm + [loud] * 5 + [quiet] * 2 + [loud] * 5)  # a cough, a gap, a cough
    assert not careful.speech_started
    run_detector(careful, [loud] * 8)
    assert careful.speech_started


# ------------------------------------------------------------ the voice loop


class ListenRecorder:
    """A recorder that can hear speech start after a delay while a reply is being spoken."""

    auto_stop = True

    def __init__(self, speech_after=None, wav=b"wav"):
        self.speech_after = speech_after
        self.wav = wav
        self.started_with = None
        self.cancelled = False
        self.stopped = 0
        self._t0 = 0.0
        self.waited = 0

    @property
    def speech_started(self):
        if self.speech_after is None:
            return False
        return asyncio.get_event_loop().time() - self._t0 >= self.speech_after

    def start(self, *, barge_in=False):
        self.started_with = barge_in
        self._t0 = asyncio.get_event_loop().time()

    def wait_done(self, timeout=40.0):
        self.waited += 1

    def cancel(self):
        self.cancelled = True

    def stop(self):
        self.stopped += 1
        return b"" if self.cancelled else self.wav

    def release(self):
        pass

    def check(self):
        pass


class SlowSpeaker:
    def __init__(self, seconds=0.5):
        self.seconds = seconds
        self.started = 0
        self.finished = 0
        self.cut = 0

    async def say(self, text):
        self.started += 1
        try:
            await asyncio.sleep(self.seconds)
        except asyncio.CancelledError:
            self.cut += 1
            raise
        self.finished += 1


class Transcribes:
    def __init__(self, text="what about tomorrow instead"):
        self.text = text
        self.calls = 0

    async def transcribe(self, wav):
        self.calls += 1
        return Transcript(self.text, 0.9)


def session(recorder, speaker, transcriber, *, barge_in=True):
    engines = Engines(transcriber, speaker, "cloud")
    out = []
    s = VoiceSession(
        object(), recorder, engines, engines, VoiceSettings(barge_in=barge_in), read=None, out=out.append
    )
    return s, out


async def test_with_interrupting_off_nothing_listens_while_it_speaks():
    rec, spk, tr = ListenRecorder(speech_after=0.0), SlowSpeaker(0.05), Transcribes()
    s, _ = session(rec, spk, tr, barge_in=False)
    assert await s._say_reply("a long reply") is None
    assert rec.started_with is None and spk.finished == 1 and tr.calls == 0


async def test_speaking_over_it_stops_the_voice_and_returns_what_was_said():
    rec, spk, tr = ListenRecorder(speech_after=0.05), SlowSpeaker(2.0), Transcribes()
    s, out = session(rec, spk, tr)
    started = asyncio.get_event_loop().time()
    heard = await s._say_reply("a very long reply that nobody wants to hear to the end")
    assert asyncio.get_event_loop().time() - started < 1.0  # cut off, not played out
    assert spk.cut == 1 and spk.finished == 0
    assert heard.text == "what about tomorrow instead" and tr.calls == 1
    assert rec.started_with is True and rec.waited == 1 and not rec.cancelled  # they were heard out
    assert any("you cut in" in line for line in out)


async def test_a_reply_nobody_talks_over_plays_to_the_end_and_the_recording_is_dropped():
    rec, spk, tr = ListenRecorder(speech_after=None), SlowSpeaker(0.1), Transcribes()
    s, _ = session(rec, spk, tr)
    assert await s._say_reply("a reply") is None
    assert spk.finished == 1 and spk.cut == 0 and rec.cancelled and tr.calls == 0


async def test_a_cut_in_with_nothing_usable_returns_nothing():
    rec, spk, tr = ListenRecorder(speech_after=0.02, wav=b""), SlowSpeaker(1.0), Transcribes()
    s, _ = session(rec, spk, tr)
    assert await s._say_reply("a reply") is None and spk.cut == 1 and tr.calls == 0


async def test_a_recorder_without_interrupt_support_just_speaks():
    class Old(ListenRecorder):
        def start(self):  # the old signature: no barge_in
            pass

    rec, spk, tr = Old(), SlowSpeaker(0.05), Transcribes()
    s, out = session(rec, spk, tr)
    assert await s._say_reply("a reply") is None and spk.finished == 1


async def test_press_b_toggles_interrupting_and_warns_about_speakers():
    s, out = session(ListenRecorder(), SlowSpeaker(), Transcribes(), barge_in=False)
    s._toggle_barge_in()
    assert s._barge_in and any("headphones" in line for line in out)
    s._toggle_barge_in()
    assert not s._barge_in and out[-1] == "  Interrupting is off."


async def test_the_local_voice_stops_talking_when_cancelled(monkeypatch):
    killed = []

    class Proc:
        async def communicate(self, data):
            await asyncio.sleep(5)

        def terminate(self):
            killed.append(True)

    async def fake_exec(*args, **kw):
        return Proc()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    task = asyncio.ensure_future(SaySpeaker().say("hello there"))
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert killed == [True]


async def test_the_audio_player_aborts_instead_of_playing_out_what_is_queued(monkeypatch):
    import sys
    import types

    events = []

    class Stream:
        def __init__(self, **kw):
            pass

        def start(self):
            events.append("start")

        def write(self, data):
            events.append("write")

        def stop(self):
            events.append("stop")

        def abort(self):
            events.append("abort")

        def close(self):
            events.append("close")

    monkeypatch.setitem(sys.modules, "sounddevice", types.SimpleNamespace(RawOutputStream=Stream))
    from sutra_orchestrator.voice.openai_engines import play_pcm_stream

    async def endless():
        while True:
            yield b"\x00\x00" * 100
            await asyncio.sleep(0.01)

    task = asyncio.ensure_future(play_pcm_stream(endless()))
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert "abort" in events and "stop" not in events and events[-1] == "close"

    events.clear()

    async def short():
        yield b"\x00\x00" * 10

    await play_pcm_stream(short())  # a reply that is left alone plays out: stop() waits for the queue
    assert "stop" in events and "abort" not in events


async def test_what_you_said_over_it_becomes_your_next_turn_and_is_answered():
    """The whole turn: the reply is cut off, and what was said over it is the next request."""
    import threading

    from sutra_orchestrator.voice.loop import VoiceSession, VoiceSettings

    heard_by_model = []

    class Lane:
        pending = None
        open_offer = None

        async def respond(self, text, **_):
            heard_by_model.append(text)
            return {"tell me about the weather": "It is a long story about the weather " * 5}.get(
                text, "Okay, tomorrow then."
            )

        async def flush(self):
            pass

        def cancel_pending(self):
            pass

        async def classify_reply(self, d, t):
            return "unclear"

    class Mic:
        """First recording: the first request. During the long reply: speech, then the interruption."""

        auto_stop = True

        def __init__(self):
            self.n = 0
            self.speech = threading.Event()
            self.mode = "listen"

        def check(self):
            pass

        def start(self, *, barge_in=False):
            self.n += 1
            self.mode = "barge" if barge_in else "listen"

        @property
        def speech_started(self):
            return self.mode == "barge"  # the user is already talking when the reply starts

        def wait_done(self, timeout=40.0):
            pass

        def cancel(self):
            self.mode = "cancelled"

        def release(self):
            pass

        def stop(self):
            return b"cut" if self.mode == "barge" else (b"first" if self.mode == "listen" and self.n == 1 else b"")

    class Says:
        def __init__(self):
            self.said = []
            self.cut = 0

        async def say(self, text):
            self.said.append(text)
            try:
                await asyncio.sleep(3)
            except asyncio.CancelledError:
                self.cut += 1
                raise

    class Hears:
        async def transcribe(self, wav):
            return Transcript({b"first": "tell me about the weather", b"cut": "no, what about tomorrow"}[wav], 0.9)

    speaker = Says()
    engines = Engines(Hears(), speaker, "cloud")
    out = []
    s = VoiceSession(Lane(), Mic(), engines, engines, VoiceSettings(barge_in=True, filler_delay=0, wait_notice_delay=0),
                     read=None, out=out.append)
    answered, carry = await s._turn()
    assert answered and speaker.cut == 1  # the long reply was cut off
    assert carry is not None and carry.text == "no, what about tomorrow"  # and is handed on as the next turn
    # The next turn takes it without listening again, and it reaches the model.
    s._recorder.mode = "listen"
    await s._turn(carry)
    assert heard_by_model == ["tell me about the weather", "no, what about tomorrow"]
