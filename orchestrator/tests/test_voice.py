"""Voice loop and engine tests, using scripted fakes (no mic, speakers, or network)."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from sutra_orchestrator.errors import ConfigError
from sutra_orchestrator.orchestrator import PendingAction
from sutra_orchestrator.voice.config import load_voice_config
from sutra_orchestrator.voice.loop import VoiceSession, VoiceSettings
from sutra_orchestrator.voice.openai_engines import OpenAISpeaker, OpenAITranscriber
from sutra_orchestrator.voice.recorder import EndpointDetector, MicRecorder, pcm_to_wav
from sutra_orchestrator.voice.types import Engines, Transcript, VoiceError


class FakeRecorder:
    def __init__(self, clips, auto_stop=False):
        self.clips = list(clips)
        self.checked = False
        self.auto_stop = auto_stop
        self.waited = 0

    def wait_done(self, timeout=40.0):
        self.waited += 1

    def cancel(self):
        pass

    def release(self):
        self.released = getattr(self, "released", 0) + 1

    def check(self):
        self.checked = True

    def start(self):
        pass

    def stop(self):
        return self.clips.pop(0)


class FakeTranscriber:
    def __init__(self, results):
        self.results = list(results)

    async def transcribe(self, wav):
        return self.results.pop(0)


class FakeSpeaker:
    def __init__(self):
        self.said = []

    async def say(self, text):
        self.said.append(text)


class StubOrchestrator:
    def __init__(self, replies, pending=None):
        self.replies = list(replies)
        self.pending = pending
        self.heard = []
        self.cancelled = False
        self.delay = 0.0

    async def respond(self, text):
        self.heard.append(text)
        await asyncio.sleep(self.delay)
        return self.replies.pop(0)

    def cancel_pending(self):
        self.pending = None
        self.cancelled = True

    async def flush(self):
        pass


def pending():
    return PendingAction("p1", "Onboard repo x", datetime.now(timezone.utc) + timedelta(minutes=2))


def make(orch, clips, transcripts, *, cloud=True, settings=None, commands=None):
    speaker, local_speaker = FakeSpeaker(), FakeSpeaker()
    local = Engines(FakeTranscriber([]), local_speaker, "local")
    eng = Engines(FakeTranscriber(transcripts), speaker, "cloud")
    lines = iter(commands or [])

    async def read(prompt):
        if prompt == "":
            return ""
        try:
            return next(lines)
        except StopIteration:
            raise EOFError from None

    out = []
    session = VoiceSession(
        orch,
        FakeRecorder(clips),
        eng if cloud else None,
        local,
        settings or VoiceSettings(filler_delay=5.0),
        read=read,
        out=out.append,
    )
    if not cloud:
        local.transcriber.results = transcripts
    return session, speaker, local_speaker, out


async def test_spoken_question_gets_spoken_reply():
    orch = StubOrchestrator(["Five projects."])
    s, speaker, _, out = make(orch, [b"wav"], [Transcript("what projects", 0.9)], commands=["", "q"])
    await s.run()
    assert orch.heard == ["what projects"]
    assert speaker.said == ["Five projects."]
    assert "sutra> Five projects." in out


async def test_empty_recording_sends_no_turn():
    orch = StubOrchestrator([])
    s, speaker, _, out = make(orch, [b""], [], commands=["", "q"])
    await s.run()
    assert orch.heard == [] and speaker.said == []
    assert any("didn't hear" in o for o in out)


async def test_transcript_without_words_sends_no_turn():
    orch = StubOrchestrator([])
    s, _, _, _ = make(orch, [b"wav"], [Transcript("  ", 0.0)], commands=["", "q"])
    await s.run()
    assert orch.heard == []


async def test_low_confidence_reply_never_reaches_orchestrator():
    orch = StubOrchestrator([], pending=pending())
    s, speaker, _, _ = make(orch, [b"w"], [Transcript("yes", 0.2)], commands=["", "q"])
    await s.run()
    assert orch.heard == []
    assert orch.pending is not None and not orch.cancelled
    assert speaker.said == ["Sorry, I didn't catch that. Was that a yes or a no?"]


async def test_clear_yes_is_read_back_then_passed_on():
    orch = StubOrchestrator(["Done."], pending=pending())
    s, speaker, _, _ = make(orch, [b"w"], [Transcript("yes", 0.95)], commands=["", "q"])
    await s.run()
    assert orch.heard == ["yes"]
    assert speaker.said[0] == "I heard: yes."


async def test_repeated_doubtful_replies_drop_the_action():
    orch = StubOrchestrator([], pending=pending())
    settings = VoiceSettings(filler_delay=5.0, reask_limit=2)
    s, speaker, _, _ = make(
        orch, [b"w"] * 3, [Transcript("mm", 0.1)] * 3, settings=settings, commands=["", "", "", "q"]
    )
    await s.run()
    assert orch.heard == []
    assert orch.cancelled
    assert "Nothing was done" in speaker.said[-1]


async def test_filler_spoken_only_when_reply_is_slow():
    orch = StubOrchestrator(["Here you go."])
    orch.delay = 0.15
    settings = VoiceSettings(filler_delay=0.02, fillers=("Hmm, one sec.",))
    s, speaker, _, _ = make(orch, [b"w"], [Transcript("q", 0.9)], settings=settings, commands=["", "q"])
    await s.run()
    assert speaker.said == ["Hmm, one sec.", "Here you go."]


async def test_no_filler_when_reply_is_fast():
    orch = StubOrchestrator(["Quick."])
    settings = VoiceSettings(filler_delay=0.5, fillers=("Hmm, one sec.",))
    s, speaker, _, _ = make(orch, [b"w"], [Transcript("q", 0.9)], settings=settings, commands=["", "q"])
    await s.run()
    assert speaker.said == ["Quick."]


async def test_private_toggle_switches_engines():
    orch = StubOrchestrator([])
    s, cloud_speaker, local_speaker, out = make(orch, [], [], commands=["p", "q"])
    await s.run()
    assert s.engines.label == "local"
    assert local_speaker.said == ["Okay, switched."] and cloud_speaker.said == []


async def test_without_cloud_key_it_is_private_and_cannot_toggle():
    orch = StubOrchestrator([])
    s, _, _, out = make(orch, [], [], cloud=False, commands=["p", "q"])
    await s.run()
    assert s.engines.label == "local"
    assert any("already private" in o for o in out)


async def test_audio_not_saved_by_default_but_saved_when_enabled(tmp_path):
    orch = StubOrchestrator(["ok", "ok"])
    s, *_ = make(orch, [b"w"], [Transcript("a", 0.9)], commands=["", "q"])
    await s.run()
    assert list(tmp_path.iterdir()) == []
    settings = VoiceSettings(filler_delay=5.0, record_dir=tmp_path)
    s, *_ = make(StubOrchestrator(["ok"]), [b"w"], [Transcript("a", 0.9)], settings=settings, commands=["", "q"])
    await s.run()
    assert len(list(tmp_path.glob("*.wav"))) == 1


async def test_microphone_failure_at_start_is_reported():
    class Broken(FakeRecorder):
        def check(self):
            raise VoiceError("could not open the microphone")

    orch = StubOrchestrator([])
    s, *_ = make(orch, [], [], commands=["q"])
    s._recorder = Broken([])
    with pytest.raises(VoiceError):
        await s.run()


# ------------------------------------------------------------------- engines


async def test_openai_transcriber_confidence_and_arguments():
    seen = {}

    class Transcriptions:
        async def create(self, **kw):
            seen.update(kw)
            lps = [SimpleNamespace(logprob=-0.1), SimpleNamespace(logprob=-0.3)]
            return SimpleNamespace(text=" hello there ", logprobs=lps)

    client = SimpleNamespace(audio=SimpleNamespace(transcriptions=Transcriptions()))
    t = OpenAITranscriber("k", prompt="Names: Sutra", client=client)
    result = await t.transcribe(b"wav")
    assert result.text == "hello there"
    assert 0.8 < result.confidence < 0.85
    assert seen["model"] == "gpt-4o-transcribe" and seen["include"] == ["logprobs"]
    assert seen["prompt"] == "Names: Sutra"


async def test_openai_transcriber_error_hides_details():
    class Transcriptions:
        async def create(self, **kw):
            raise RuntimeError("secret sk-123 leaked in message")

    client = SimpleNamespace(audio=SimpleNamespace(transcriptions=Transcriptions()))
    with pytest.raises(VoiceError) as exc:
        await OpenAITranscriber("k", client=client).transcribe(b"wav")
    assert "sk-123" not in str(exc.value)


async def test_openai_speaker_streams_pcm_to_the_player():
    played = []

    class Stream:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def iter_bytes(self, size):
            for chunk in (b"\x01\x00\x02\x00", b"\x03\x00"):
                yield chunk

    class Speech:
        class with_streaming_response:  # noqa: N801
            @staticmethod
            def create(**kw):
                assert kw["model"] == "gpt-4o-mini-tts" and kw["response_format"] == "pcm"
                return Stream()

    async def play(chunks):
        async for c in chunks:
            played.append(c)

    client = SimpleNamespace(audio=SimpleNamespace(speech=Speech()))
    await OpenAISpeaker("k", client=client, play=play).say("hi")
    assert played == [b"\x01\x00\x02\x00", b"\x03\x00"]


def test_pcm_to_wav_and_silence_detection():
    wav = pcm_to_wav(b"\x01\x00" * 100)
    assert wav[:4] == b"RIFF"
    rec = MicRecorder()
    rec._chunks = [bytes(16_000 * 2)]  # one second of pure zeros
    with pytest.raises(VoiceError):
        rec.stop()
    rec._chunks = [b"\x01\x00" * 100]  # too short
    assert rec.stop() == b""


def test_voice_config_defaults_and_validation():
    c = load_voice_config({}, dotenv_path=None)
    assert c.assistant_name == "Sutra" and not c.start_private and c.openai_api_key == ""
    assert "sk-secret" not in repr(load_voice_config({"OPENAI_API_KEY": "sk-secret"}, dotenv_path=None))
    with pytest.raises(ConfigError):
        load_voice_config({"SUTRA_VOICE_MODE": "loud"}, dotenv_path=None)
    with pytest.raises(ConfigError):
        load_voice_config({"SUTRA_MIN_CONFIDENCE": "2"}, dotenv_path=None)


# ------------------------------------------------- end-of-speech and conversation mode


def run_detector(levels, **kw):
    det = EndpointDetector(**kw)
    for i, level in enumerate(levels):
        if det.feed(level):
            return i, det
    return None, det


QUIET, LOUD = 20.0, 3000.0


def test_detector_stops_after_silence_following_speech():
    levels = [QUIET] * 10 + [LOUD] * 20 + [QUIET] * 60
    stop, det = run_detector(levels, silence_ms=900)
    assert det.speech_started
    assert stop is not None and 30 + 25 < stop <= 30 + 35  # ~900ms of quiet after speech


def test_detector_keeps_listening_through_a_short_pause():
    levels = [QUIET] * 10 + [LOUD] * 20 + [QUIET] * 20 + [LOUD] * 20 + [QUIET] * 5
    stop, _ = run_detector(levels, silence_ms=1200)
    assert stop is None  # a 600ms thinking pause does not end the turn


def test_detector_gives_up_when_nobody_speaks():
    stop, det = run_detector([QUIET] * 400, no_speech_ms=3000)
    assert not det.speech_started and stop is not None


def test_detector_ignores_a_single_click():
    levels = [QUIET] * 10 + [LOUD] + [QUIET] * 400
    _, det = run_detector(levels, no_speech_ms=3000)
    assert not det.speech_started


def test_detector_adapts_to_a_noisy_room():
    noisy = 400.0
    levels = [noisy] * 10 + [noisy * 1.2] * 30 + [LOUD] * 10
    _, det = run_detector(levels)
    assert det.speech_started  # only the real speech counts, not the room hum








async def test_memory_flush_does_not_delay_listening():
    flushed = asyncio.Event()

    class SlowFlush(StubOrchestrator):
        async def flush(self):
            await asyncio.sleep(0.3)
            flushed.set()

    orch = SlowFlush(["Hi."])
    s, *_ = make(orch, [b"w"], [Transcript("hello", 0.9)], commands=["", "q"])
    started = asyncio.get_running_loop().time()
    await s.run()
    assert asyncio.get_running_loop().time() - started < 0.25  # run() did not wait for the flush
    assert not flushed.is_set()
    await s.close()
    assert flushed.is_set()  # but nothing is lost on exit




def test_detector_does_not_mistake_immediate_speech_for_noise():
    levels = [LOUD] * 30 + [QUIET] * 60  # talking from the very first block
    stop, det = run_detector(levels, silence_ms=900)
    assert det.speech_started and stop is not None


# ===================================================== background jobs and listening
#
# These use a timing-based microphone and conversation lanes so the loop's concurrency
# (listening while a request runs) is exercised for real.

import threading  # noqa: E402

from sutra_orchestrator.voice.loop import BUSY_LINE  # noqa: E402


class ScriptMic:
    """A microphone that 'hears' scripted clips after scripted delays.

    Each ``start()`` consumes one (delay, wav) entry. A delay of None means nobody speaks:
    the recording lasts until cancelled (or a short safety timeout).
    """

    auto_stop = True

    def __init__(self, script):
        self.script = list(script)
        self.cancelled = threading.Event()
        self.current = (None, b"")
        self.starts = 0
        self.released = 0

    def check(self):
        pass

    def start(self):
        self.cancelled.clear()
        self.starts += 1
        self.current = self.script.pop(0) if self.script else (None, b"")

    def wait_done(self, timeout=40.0):
        delay, _ = self.current
        self.cancelled.wait(0.6 if delay is None else delay)

    def cancel(self):
        self.cancelled.set()

    def release(self):
        self.released += 1

    def stop(self):
        delay, wav = self.current
        if self.cancelled.is_set() or delay is None:
            return b""
        return wav


class MapTranscriber:
    def __init__(self, table):
        self.table = table

    async def transcribe(self, wav):
        return self.table[wav]


class Lane:
    """A conversation lane stub. ``shared`` maps an utterance to (delay, reply, holds_action)."""

    count = 0

    def __init__(self, shared):
        self.shared = shared
        self.id = len(shared["lanes"])
        shared["lanes"].append(self)
        self.pending = None
        self.notes = []

    async def respond(self, text):
        self.shared["heard"].append((self.id, text))
        delay, reply, holds = self.shared["responses"][text]
        await asyncio.sleep(delay)
        if holds:
            self.pending = pending()
        elif self.pending is not None:
            self.pending = None
        return reply

    def fork(self):
        return Lane(self.shared)

    def cancel_pending(self):
        self.pending = None

    async def flush(self):
        pass

    async def classify_reply(self, description, text):
        return self.shared["labels"].get(text, "unclear")

    def note_background_result(self, request, reply):
        self.notes.append((request, reply))


def build(script, table, responses, *, labels=None, commands=None, settings=None):
    shared = {"lanes": [], "heard": [], "responses": responses, "labels": labels or {}}
    fg = Lane(shared)
    mic = ScriptMic(script)
    speaker = FakeSpeaker()
    eng = Engines(MapTranscriber(table), speaker, "cloud")
    cmds = list(commands or [("", 0), ("q", 0)])

    async def read(prompt):
        if prompt == "":
            return ""
        if not cmds:
            raise EOFError
        text, delay = cmds.pop(0)
        await asyncio.sleep(delay)
        return text

    out = []
    cfg = settings or VoiceSettings(filler_delay=0, wait_notice_delay=0, max_background=2)
    session = VoiceSession(fg, mic, eng, eng, cfg, read=read, out=out.append)
    return session, shared, mic, speaker, out


def T(text, conf=0.9):
    return Transcript(text, conf)


async def test_speaking_during_a_slow_request_detaches_it_and_answers_the_new_question():
    s, shared, mic, speaker, out = build(
        # turn, interrupting speech, (silence while the quick answer is worked out),
        # (silence until the conversation goes idle), then the answer to "want it now?"
        [(0.0, b"a"), (0.1, b"b"), (None, b""), (None, b""), (0.0, b"c")],
        {b"a": T("slow question please"), b"b": T("quick question please"), b"c": T("yes please")},
        {
            "slow question please": (0.5, "Slow answer.", False),
            "quick question please": (0.0, "Quick answer.", False),
        },
        labels={"yes please": "affirm"},
        commands=[("", 0), ("q", 1.2)],
    )
    await s.run()
    assert (0, "slow question please") in shared["heard"]
    assert (1, "quick question please") in shared["heard"]  # answered on a fresh lane
    said = speaker.said
    assert said.index("Quick answer.") < said.index(
        next(x for x in said if "answer to your earlier request" in x)
    )
    assert said[-1] == "Slow answer."  # only spoken after the user said yes
    assert s._fg.notes == [("slow question please", "Slow answer.")]


async def test_finished_background_work_is_never_spoken_without_asking():
    s, shared, mic, speaker, out = build(
        [(0.0, b"a"), (0.1, b"b")],
        {b"a": T("slow question please"), b"b": T("quick question please")},
        {
            "slow question please": (0.4, "Slow answer.", False),
            "quick question please": (0.0, "Quick answer.", False),
        },
        commands=[("", 0), ("q", 1.2)],
    )
    await s.run()
    assert "Slow answer." not in speaker.said  # asked, got no answer, kept for later
    assert any("Want it now?" in x for x in speaker.said)


async def test_declining_keeps_it_and_what_came_back_asks_again():
    s, shared, mic, speaker, out = build(
        [(0.0, b"a"), (0.1, b"b"), (None, b""), (None, b""), (0.0, b"c"), (0.0, b"d")],
        {
            b"a": T("slow question please"),
            b"b": T("quick question please"),
            b"c": T("not right now"),
            b"d": T("what came back"),
        },
        {
            "slow question please": (0.4, "Slow answer.", False),
            "quick question please": (0.0, "Quick answer.", False),
        },
        labels={"not right now": "deny"},
        commands=[("", 0), ("", 0.9), ("q", 0.3)],
    )
    await s.run()
    assert "Okay, later." in speaker.said
    assert sum("Want it now?" in x for x in speaker.said) == 2  # offered, declined, asked for again


async def test_at_the_background_limit_the_new_question_is_declined_and_work_continues():
    s, shared, mic, speaker, out = build(
        [(0.0, b"a"), (0.1, b"b")],
        {b"a": T("slow question please"), b"b": T("quick question please")},
        {"slow question please": (0.4, "Slow answer.", False)},
        settings=VoiceSettings(filler_delay=0, wait_notice_delay=0, max_background=0),
        commands=[("", 0), ("q", 0.1)],
    )
    await s.run()
    assert BUSY_LINE in speaker.said
    assert "Slow answer." in speaker.said  # the original request was not dropped
    assert all(text != "quick question please" for _, text in shared["heard"])


async def test_noise_does_not_interrupt_a_request():
    s, shared, mic, speaker, out = build(
        [(0.0, b"a"), (0.1, b"b")],
        {b"a": T("slow question please"), b"b": T("uh", 0.9)},  # one word: not an interruption
        {"slow question please": (0.4, "Slow answer.", False)},
        commands=[("", 0), ("q", 0.1)],
    )
    await s.run()
    assert [h for h in shared["heard"]] == [(0, "slow question please")]
    assert "Slow answer." in speaker.said


async def test_wait_notice_and_filler_are_spoken_for_slow_requests_only():
    s, shared, mic, speaker, out = build(
        [(0.0, b"a")],
        {b"a": T("slow question please")},
        {"slow question please": (0.5, "Slow answer.", False)},
        settings=VoiceSettings(filler_delay=0.1, wait_notice_delay=0.25, fillers=("Hmm, one sec.",)),
        commands=[("", 0), ("q", 0.1)],
    )
    await s.run()
    assert speaker.said[0] == "Hmm, one sec."
    assert "ask me something else" in speaker.said[1]
    assert speaker.said[-1] == "Slow answer."


async def test_no_wait_notice_for_a_fast_request():
    s, shared, mic, speaker, out = build(
        [(0.0, b"a")],
        {b"a": T("quick question please")},
        {"quick question please": (0.0, "Quick answer.", False)},
        settings=VoiceSettings(filler_delay=0.2, wait_notice_delay=0.4, fillers=("Hmm, one sec.",)),
        commands=[("", 0), ("q", 0.1)],
    )
    await s.run()
    assert speaker.said == ["Quick answer."]


async def test_a_background_action_needing_confirmation_is_asked_about_and_routed_to_its_lane():
    s, shared, mic, speaker, out = build(
        [(0.0, b"a"), (0.1, b"b"), (None, b""), (None, b""), (0.0, b"c"), (0.0, b"d")],
        {
            b"a": T("onboard that repo now"),
            b"b": T("quick question please"),
            b"c": T("yes go ahead"),
            b"d": T("yes do it"),
        },
        {
            "onboard that repo now": (0.4, "Onboard repo x. Yes or no?", True),
            "quick question please": (0.0, "Quick answer.", False),
            "yes do it": (0.0, "Done.", False),
        },
        labels={"yes go ahead": "affirm"},
        commands=[("", 0), ("", 0.9), ("q", 0.3)],
    )
    await s.run()
    assert any("go-ahead" in x for x in speaker.said)
    assert "Onboard repo x. Yes or no?" in speaker.said
    # the final yes was handled by the lane that holds the action (lane 0), not the main lane
    assert (0, "yes do it") in shared["heard"]
    assert "Done." in speaker.said


async def test_a_second_action_is_not_offered_while_one_awaits_confirmation():
    from sutra_orchestrator.voice.loop import Job, Notice

    s, shared, *_ = build([], {}, {})
    s._fg.pending = pending()  # one action already awaits confirmation
    job = Job("x", "x", Lane(shared), asyncio.get_running_loop().create_future())
    s._ready.append(Notice(job, "confirm", "Do it?"))
    assert s._next_offerable() is None  # held back until the first action is settled
    s._fg.pending = None
    assert s._next_offerable() is not None


async def test_session_close_waits_for_running_jobs():
    s, shared, mic, speaker, out = build(
        [(0.0, b"a"), (0.1, b"b"), (None, b""), (None, b"")],
        {b"a": T("slow question please"), b"b": T("quick question please")},
        {
            "slow question please": (1.2, "Slow answer.", False),
            "quick question please": (0.0, "Quick answer.", False),
        },
        commands=[("", 0), ("q", 0.05)],
    )
    await s.run()
    assert len(s._jobs) == 1
    await s.close()
    assert s._jobs == [] and len(s._ready) == 1


async def test_microphone_is_released_when_the_conversation_ends():
    s, shared, mic, speaker, out = build(
        [(0.0, b"a")],
        {b"a": T("quick question please")},
        {"quick question please": (0.0, "Quick answer.", False)},
        commands=[("", 0), ("q", 0.1)],
    )
    await s.run()
    assert mic.released == 1 and speaker.said == ["Quick answer."]


async def test_conversation_mode_off_takes_one_turn_per_enter():
    s, shared, mic, speaker, out = build(
        [(0.0, b"a"), (None, b""), (0.0, b"b")],
        {b"a": T("first question please"), b"b": T("second question please")},
        {
            "first question please": (0.0, "One.", False),
            "second question please": (0.0, "Two.", False),
        },
        settings=VoiceSettings(filler_delay=0, wait_notice_delay=0, conversation=False),
        commands=[("", 0), ("q", 0.1)],
    )
    await s.run()
    assert speaker.said == ["One."]


async def test_a_fired_reminder_is_spoken_without_asking_and_marked_heard():
    s, shared, mic, speaker, out = build([], {}, {}, commands=[("", 0.3), ("q", 0.1)])
    heard = []
    s._on_reminder_spoken = heard.append
    s.deliver_reminder("e1", "call Sam")
    s.deliver_reminder("e2", "water the plants", late=True)
    await s.run()
    assert speaker.said == [
        "Reminder: call Sam.",
        "Sorry, this one is late. You asked me to remind you: water the plants.",
    ]
    assert heard == ["e1", "e2"]
