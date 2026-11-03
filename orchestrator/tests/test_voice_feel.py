"""Voice feel: sentences spoken as they are written, instant cached fillers, delivery style, timing."""

from __future__ import annotations

import asyncio
import logging
from types import SimpleNamespace

import pytest

from sutra_orchestrator.model import ModelResponse
from sutra_orchestrator.streaming import SentenceSplitter, Streamer
from sutra_orchestrator.voice.config import load_voice_config
from sutra_orchestrator.voice.loop import Streamed, VoiceSession, VoiceSettings
from sutra_orchestrator.voice.openai_engines import CACHE_PHRASES, DEFAULT_TTS_INSTRUCTIONS, OpenAISpeaker
from sutra_orchestrator.voice.types import Engines, Transcript

from .fakes import Clock, FakeGateway, default_tools, make_orchestrator, text, tool_use

# --------------------------------------------------------------- splitter, streamer


def feed_all(text_, size=7):
    s = SentenceSplitter()
    out = []
    for i in range(0, len(text_), size):
        out += s.feed(text_[i : i + size])
    return out, s.flush()


def test_sentences_are_not_split_at_abbreviations_or_decimals():
    out, rest = feed_all("Dr. Rao is free at 3.5 percent, around 5 p.m. today. That works well for you! Want me to book it?")
    assert out == ["Dr. Rao is free at 3.5 percent, around 5 p.m. today.", "That works well for you!"]
    assert rest == "Want me to book it?"


def test_short_sentences_are_joined_so_speech_is_not_choppy():
    out, rest = feed_all("Okay. Sure thing. I can look that up for you right now. Anything else?")
    assert out[0] == "Okay. Sure thing. I can look that up for you right now."
    assert rest == "Anything else?"


def test_a_sentence_is_released_only_once_the_next_one_has_begun():
    got = []
    st = Streamer(got.append)
    st.feed("The first full sentence is right here. ")
    assert got == []  # held: nothing has followed it yet, and a tool call might
    st.feed("The")
    assert got == ["The first full sentence is right here."]  # the next one has begun: safe to say
    st.feed(" second full sentence follows it. And")
    st.feed(" a third one is on the way now.")
    st.finish("end_turn")
    assert got == [
        "The first full sentence is right here.",
        "The second full sentence follows it.",
        "And a third one is on the way now.",
    ]


def test_a_single_sentence_before_a_tool_call_is_never_spoken():
    got = []
    st = Streamer(got.append)
    st.feed("Let me look at that for you right now.")
    st.finish("tool_use")
    assert got == []


def test_a_longer_lead_in_speaks_all_but_its_last_sentence_which_is_documented_and_harmless():
    got = []
    st = Streamer(got.append)
    st.feed("Let me look at that for you right now. One moment please while I check.")
    st.finish("tool_use")
    assert got == ["Let me look at that for you right now."]  # the voice client will not repeat it (see Streamed)


def test_a_failing_listener_never_breaks_the_stream():
    def boom(_):
        raise RuntimeError("listener broke")

    st = Streamer(boom)
    st.feed("A reasonably long first sentence goes here. A reasonably long second sentence goes here.")
    st.finish("end_turn")  # must not raise


# ------------------------------------------------------------ the orchestrator


class StreamingModel:
    """Writes each scripted step in small deltas. A step is text, optionally ending in a tool call."""

    def __init__(self, steps):
        self.steps = list(steps)
        self.calls = 0
        self.gate = None  # an event the model waits on before finishing the last step

    async def complete(self, *, system, messages, tools, allow_tools=True, on_text=None):
        self.calls += 1
        content, stop = self.steps.pop(0)
        blocks = [text(content)] if content else []
        for i in range(0, len(content), 6):
            if on_text:
                on_text(content[i : i + 6])
            await asyncio.sleep(0)
        if self.gate is not None and not self.steps:
            await self.gate.wait()
        if stop == "tool_use":
            blocks.append(tool_use("finanxe_list_debts"))
        return ModelResponse(content=blocks, stop_reason=stop)

    async def classify(self, *, system, user):
        return "unclear"


async def test_the_reply_is_streamed_while_the_model_is_still_writing_and_returned_whole():
    reply_text = "I looked at it carefully today. The short answer is yes. There is one catch though."
    model = StreamingModel([(reply_text, "end_turn")])
    model.gate = asyncio.Event()
    orch, _ = await make_orchestrator(model)
    got: list[str] = []
    work = asyncio.ensure_future(orch.respond("how is it", on_text=got.append))
    for _ in range(200):
        await asyncio.sleep(0)
        if got:
            break
    assert got == ["I looked at it carefully today."]  # spoken before the model has finished
    assert not work.done()
    model.gate.set()
    reply = await work
    assert reply == reply_text
    assert got[-1] == "There is one catch though." and " ".join(got) == reply_text  # nothing lost or repeated


async def test_text_before_a_tool_call_is_dropped_and_the_final_answer_is_what_is_streamed():
    gateway = FakeGateway(tools=default_tools(), results={"finanxe_list_debts": SimpleNamespace(kind="ok", text="[]")})
    model = StreamingModel(
        [
            ("Let me look at your debts for you right now.", "tool_use"),
            ("You have no debts at all, which is great news today.", "end_turn"),
        ]
    )
    orch, _ = await make_orchestrator(model, gateway)
    got: list[str] = []
    reply = await orch.respond("what debts do I have", on_text=got.append)
    assert reply == "You have no debts at all, which is great news today."
    assert got == [reply]  # the lead-in before the tool call was never spoken


async def test_a_model_that_cannot_stream_still_works_and_text_mode_is_unchanged():
    from .fakes import FakeModel, resp

    model = FakeModel([resp(text("Plain reply here.")), resp(text("Again."))])
    orch, _ = await make_orchestrator(model)
    got: list[str] = []
    assert await orch.respond("hi there", on_text=got.append) == "Plain reply here."
    assert got == []  # this model has no streaming: the caller speaks the whole reply
    assert await orch.respond("and again") == "Again."


# ------------------------------------------------------------------- the voice loop


class Lane:
    """A conversation lane that writes its reply in sentences over time."""

    pending = None
    open_offer = None

    def __init__(self, sentences, *, gap=0.05, tail=""):
        self.sentences = sentences
        self.gap = gap
        self.tail = tail  # appended after streaming, like an offer
        self.finished = False

    async def respond(self, text_, on_text=None, **_):
        for s in self.sentences:
            await asyncio.sleep(self.gap)
            if on_text:
                on_text(s)
        await asyncio.sleep(self.gap)
        self.finished = True
        return " ".join(self.sentences) + (" " + self.tail if self.tail else "")

    async def flush(self):
        pass

    def cancel_pending(self):
        pass

    async def classify_reply(self, d, t):
        return "unclear"

    def fork(self):
        return self


class Mic:
    """First listen yields the request; while speaking, speech can start after N sentences."""

    auto_stop = True

    def __init__(self, cut_after=None, spoken=None):
        self.cut_after = cut_after
        self.spoken = spoken
        self.n = 0
        self.mode = "idle"

    def check(self):
        pass

    def start(self, *, barge_in=False):
        self.n += 1
        self.mode = "barge" if barge_in else "listen"

    @property
    def speech_started(self):
        return self.mode == "barge" and self.cut_after is not None and len(self.spoken) >= self.cut_after

    def wait_done(self, timeout=40.0):
        pass

    def cancel(self):
        self.mode = "cancelled"

    def release(self):
        pass

    def stop(self):
        if self.mode == "barge":
            return b"cut"
        return b"first" if self.n == 1 else b""


class Voice:
    def __init__(self, *, slow=0.0, fail_first=False):
        self.said = []
        self.slow = slow
        self.fail_first = fail_first
        self.cut = 0

    async def say(self, text_):
        if self.fail_first:
            self.fail_first = False
            raise RuntimeError("synthesis blew up")
        self.said.append(text_)
        try:
            await asyncio.sleep(self.slow)
        except asyncio.CancelledError:
            self.cut += 1
            raise


class Hears:
    async def transcribe(self, wav):
        return Transcript({b"first": "tell me about it", b"cut": "no wait, something else"}[wav], 0.9)


def make_voice(lane, *, mic=None, voice=None, stream=True, barge_in=False, fillers=("Hmm, one sec.",), filler_delay=0.0):
    voice = voice or Voice()
    mic = mic or Mic()
    mic.spoken = voice.said
    engines = Engines(Hears(), voice, "cloud")
    settings = VoiceSettings(
        stream=stream, barge_in=barge_in, filler_delay=filler_delay, wait_notice_delay=0.0, fillers=fillers
    )
    out = []
    return VoiceSession(lane, mic, engines, engines, settings, read=None, out=out.append), voice, out


S1 = "First I looked at the whole picture carefully."
S2 = "Second there is one thing that stands out here."
S3 = "Third you should probably decide by Friday."


async def test_sentences_are_spoken_in_order_as_they_are_written():
    lane = Lane([S1, S2, S3], gap=0.05)
    s, voice, out = make_voice(lane)
    answered, carry = await s._turn()
    assert answered and carry is None
    assert voice.said == [S1, S2, S3]  # nothing repeated, nothing lost
    assert lane.finished


async def test_something_appended_after_the_stream_is_spoken_once_after_it():
    lane = Lane([S1, S2], tail="By the way, want a quick example of that?")
    s, voice, out = make_voice(lane)
    await s._turn()
    assert voice.said == [S1, S2, "By the way, want a quick example of that?"]


async def test_no_filler_is_spoken_when_the_first_sentence_comes_quickly():
    lane = Lane([S1, S2], gap=0.01)
    s, voice, out = make_voice(lane, filler_delay=0.5)
    await s._turn()
    assert "Hmm, one sec." not in voice.said and voice.said[0] == S1


async def test_a_slow_start_still_gets_its_filler_then_the_reply():
    lane = Lane([S1, S2], gap=0.3)
    s, voice, out = make_voice(lane, filler_delay=0.1)
    await s._turn()
    assert voice.said[0] == "Hmm, one sec." and voice.said[1:] == [S1, S2]


async def test_speaking_over_a_streamed_reply_stops_it_and_hands_over_the_next_turn():
    lane = Lane([S1, S2, S3], gap=0.05)
    mic = Mic(cut_after=1)
    s, voice, out = make_voice(lane, mic=mic, voice=Voice(slow=0.3), barge_in=True)
    answered, carry = await s._turn()
    assert voice.said == [S1] and voice.cut == 1  # cut off mid-first-sentence; the rest was never said
    assert carry is not None and carry.text == "no wait, something else"
    assert lane.finished  # the model was left to finish, so the history stays whole


async def test_without_streaming_the_whole_reply_is_spoken_at_the_end():
    lane = Lane([S1, S2, S3], gap=0.02)
    s, voice, out = make_voice(lane, stream=False)
    await s._turn()
    assert voice.said == [" ".join([S1, S2, S3])]


async def test_if_streamed_speech_fails_the_whole_reply_is_still_spoken():
    lane = Lane([S1, S2], gap=0.02)
    s, voice, out = make_voice(lane, voice=Voice(fail_first=True))
    answered, _ = await s._turn()
    assert answered and voice.said == [" ".join([S1, S2])]  # not muted


def test_streamed_remainder_rules():
    r = Streamed("One two three. And a bonus offer.")
    r.spoken, r.cut = ["One two three."], False
    assert r.remainder() == "And a bonus offer."
    r.spoken = ["Something else entirely."]
    assert r.remainder() == "One two three. And a bonus offer."  # not the start: say it all
    r.spoken = ["One two three.", "And a bonus offer."]
    assert r.remainder() == ""
    # A lead-in sentence spoken before a tool call is not part of the reply: it must not cause a repeat.
    leaked = Streamed("The answer is forty two. Want more?")
    leaked.spoken, leaked.cut = ["Let me check that for you.", "The answer is forty two."], False
    assert leaked.remainder() == "Want more?"


async def test_timings_are_logged_only_in_debug(caplog):
    lane = Lane([S1, S2], gap=0.01)
    s, voice, out = make_voice(lane)
    with caplog.at_level(logging.DEBUG, logger="sutra_orchestrator"):
        await s._turn()
    lines = [r.getMessage() for r in caplog.records if "turn timing" in r.getMessage()]
    assert len(lines) == 1 and "transcribe" in lines[0] and "first words" in lines[0]
    assert not any("turn timing" in line for line in out)  # nothing extra is shown to the user


# --------------------------------------------------- cached acknowledgements, style


def fake_openai(created):
    class Stream:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def iter_bytes(self, size):
            yield b"\x01\x00\x02\x00"
            yield b"\x03\x00"

    class Speech:
        class with_streaming_response:  # noqa: N801
            @staticmethod
            def create(**kw):
                created.append(kw)
                return Stream()

    return SimpleNamespace(audio=SimpleNamespace(speech=Speech()))


async def test_a_short_phrase_is_synthesized_once_and_replayed_from_memory():
    created, played = [], []

    async def play(chunks):
        played.append(b"".join([c async for c in chunks]))

    speaker = OpenAISpeaker("k", client=fake_openai(created), play=play)
    await speaker.say("Hmm, one sec.")
    await speaker.say("Hmm, one sec.")
    assert len(created) == 1  # the second time is instant: no network
    assert played[0] == played[1] == b"\x01\x00\x02\x00\x03\x00"
    long_reply = "This is a long reply that is certainly not a short filler phrase at all."
    await speaker.say(long_reply)
    await speaker.say(long_reply)
    assert len(created) == 3  # long text is never cached


async def test_prewarm_makes_the_first_use_instant_and_a_failure_is_harmless():
    created = []

    async def play(chunks):
        [c async for c in chunks]

    speaker = OpenAISpeaker("k", client=fake_openai(created), play=play)
    await speaker.prewarm(["Hmm, one sec.", "Let me think."])
    assert len(created) == 2
    await speaker.say("Let me think.")
    assert len(created) == 2

    class Broken:
        class audio:  # noqa: N801
            class speech:  # noqa: N801
                class with_streaming_response:  # noqa: N801
                    @staticmethod
                    def create(**kw):
                        raise OSError("no network")

    await OpenAISpeaker("k", client=Broken(), play=play).prewarm(["Hmm."])  # must not raise


async def test_the_cache_is_capped_and_a_cut_off_phrase_is_not_kept():
    created = []

    async def play(chunks):
        [c async for c in chunks]

    speaker = OpenAISpeaker("k", client=fake_openai(created), play=play)
    for i in range(CACHE_PHRASES + 5):
        await speaker.say(f"Phrase number {i}.")
    assert len(speaker._cache) == CACHE_PHRASES

    async def cut_play(chunks):
        async for _ in chunks:
            raise asyncio.CancelledError  # the user spoke over it

    cut = OpenAISpeaker("k", client=fake_openai([]), play=cut_play)
    with pytest.raises(asyncio.CancelledError):
        await cut.say("Hmm, one sec.")
    assert cut._cache == {}


async def test_delivery_style_comes_from_the_setting_and_has_a_warmer_default():
    created = []

    async def play(chunks):
        [c async for c in chunks]

    await OpenAISpeaker("k", client=fake_openai(created), play=play).say("Hello there.")
    assert created[-1]["instructions"] == DEFAULT_TTS_INSTRUCTIONS and "Vary your pitch" in DEFAULT_TTS_INSTRUCTIONS
    await OpenAISpeaker("k", client=fake_openai(created), play=play, instructions="Whisper everything.").say("Hi.")
    assert created[-1]["instructions"] == "Whisper everything."
    cfg = load_voice_config({"SUTRA_TTS_STYLE": " Speak slowly. ", "SUTRA_STREAM_REPLY": "off"}, dotenv_path=None)
    assert cfg.tts_style == "Speak slowly." and cfg.stream_reply is False
    default = load_voice_config({}, dotenv_path=None)
    assert default.tts_style == "" and default.stream_reply is True and default.filler_delay == 1.0
