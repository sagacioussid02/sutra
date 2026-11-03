"""Modes (full, limited, off), the silent distress phrase, tool limits, and wake-word activation."""

from __future__ import annotations

import asyncio
import json
import os
import stat
from datetime import timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from sutra_orchestrator.config import load_config
from sutra_orchestrator.errors import ConfigError
from sutra_orchestrator.feeds import FeedService
from sutra_orchestrator.hangout import HangoutService, Line
from sutra_orchestrator.idle.service import IdleResearcher
from sutra_orchestrator.offers import OffersService, OffersStore
from sutra_orchestrator.orchestrator import HANGOUT_LIMITED_REPLY
from sutra_orchestrator.safety import (
    DROPPED_REPLY,
    LIMITED_REPLY,
    OFF_REPLY,
    OFF_REPLY_HI,
    RAISE_REPLY,
    Mode,
    ModeCommands,
    SafetyService,
)
from sutra_orchestrator.voice.loop import VoiceSession, VoiceSettings
from sutra_orchestrator.voice.types import Engines, Transcript, VoiceError
from sutra_orchestrator.voice.wake import WakeMatcher

from .fakes import Clock, FakeGateway, FakeModel, default_tools, make_orchestrator, pending, resp, text, tool_use
from .test_idle import make as make_idle

UTC = ZoneInfo("UTC")
PHRASE = "the blue heron flies at noon"


def make(tmp_path, **kw):
    return SafetyService(tmp_path / "s", **kw)


# ------------------------------------------------------------- the mode itself


def test_the_mode_is_saved_privately_and_a_restart_does_not_raise_it(tmp_path):
    s = make(tmp_path)
    assert s.mode is Mode.FULL and s.proactive_ok
    assert s.lower(Mode.LIMITED) and not s.lower(Mode.LIMITED) and not s.lower(Mode.FULL)  # lowering only
    assert stat.S_IMODE(os.stat(tmp_path / "s" / "mode.json").st_mode) == 0o600
    again = make(tmp_path, start=Mode.FULL)
    assert again.mode is Mode.LIMITED  # the saved mode wins over the configured start
    again.restore(Mode.FULL)  # only the keyboard path can raise it
    assert make(tmp_path).mode is Mode.FULL


def test_a_damaged_or_unreadable_file_fails_safe(tmp_path):
    (tmp_path / "s").mkdir()
    for bad in ("{not json", '{"mode": "turbo"}', "[]", '{"nope": 1}'):
        (tmp_path / "s" / "mode.json").write_text(bad)
        assert make(tmp_path).mode is Mode.LIMITED


def test_listeners_hear_changes_and_a_broken_one_cannot_stop_them(tmp_path):
    s = make(tmp_path)
    seen = []
    s.on_change(lambda m: 1 / 0)
    s.on_change(seen.append)
    s.lower(Mode.OFF)
    assert seen == [Mode.OFF]


@pytest.mark.parametrize(
    "said,target",
    [
        ("safe mode", Mode.LIMITED), ("Limited mode please", Mode.LIMITED), ("hey Sutra, go to safe mode", Mode.LIMITED),
        ("switch to read only mode now", Mode.LIMITED), ("सेफ मोड", Mode.LIMITED),
        ("go quiet", Mode.OFF), ("Sutra, stop listening", Mode.OFF), ("mute yourself", Mode.OFF), ("switch yourself off", Mode.OFF),
        ("चुप हो जाओ", Mode.OFF), ("sunna band karo", Mode.OFF),
    ],
)
def test_lowering_keywords(tmp_path, said, target):
    c = make(tmp_path).command(said)
    assert c is not None and c.kind == "keyword" and c.target is target and c.announce


@pytest.mark.parametrize(
    "said",
    [
        "I want to talk about the safe mode setting on my car", "the limited mode of the washing machine is broken",
        "please don't go quiet on me during the call", "can you stop listening to music for me", "what is full mode",
    ],
)
def test_a_keyword_inside_a_longer_sentence_does_nothing(tmp_path, said):
    assert make(tmp_path).command(said) is None


def test_raising_is_never_done_by_voice_only_recognized_as_an_attempt(tmp_path):
    s = make(tmp_path)
    assert s.command("full mode") is None and s.command("wake up") is None  # in full mode these are just words
    s.lower(Mode.LIMITED)
    for said in ("full mode", "wake up", "unmute yourself", "Sutra, come back"):
        c = s.command(said)
        assert c.kind == "raise_attempt" and c.target is None
    assert s.mode is Mode.LIMITED


def test_the_distress_phrase_is_found_anywhere_cut_out_and_never_shown(tmp_path):
    s = make(tmp_path, duress_phrase=PHRASE)
    c = s.command("Transfer 500 dollars, The Blue Heron flies at noon!, thanks")
    assert c.kind == "duress" and c.target is Mode.LIMITED and not c.announce
    assert c.text == "Transfer 500 dollars, thanks" and PHRASE not in c.text.lower()
    assert s.command("the blue heron flies at moon") is None  # a near miss is not it
    cfg = load_config({"SUTRA_TOKEN": "t", "ANTHROPIC_API_KEY": "k", "SUTRA_DURESS_PHRASE": PHRASE}, dotenv_path=None)
    assert cfg.duress_phrase == PHRASE and PHRASE not in repr(cfg) and "heron" not in repr(cfg)
    with pytest.raises(ConfigError):
        load_config({"SUTRA_TOKEN": "t", "ANTHROPIC_API_KEY": "k", "SUTRA_DURESS_PHRASE": "yes"}, dotenv_path=None)


def test_limited_mode_lets_only_reads_through_and_fails_closed(tmp_path):
    s = make(tmp_path, extra_tools=("twin_chat",))
    s.lower(Mode.LIMITED)
    allowed = ["finanxe_list_debts", "finanxe_get_snapshot", "finanxe_get_calendar", "twin_list_public_personas", "twin_chat"]
    blocked = ["finanxe_create_goal", "finanxe_add_calendar_event", "finanxe_set_debt_funding", "echo", "mutate", "finanxe_listify", "get", "gateway_confirm"]
    assert all(s.tool_allowed(n, local=False) for n in allowed)
    assert not any(s.tool_allowed(n, local=False) for n in blocked)
    assert s.tool_allowed("stop_offers", local=True) and not s.tool_allowed("delegate_research", local=True)
    s.restore(Mode.OFF)
    assert not s.tool_allowed("finanxe_list_debts", local=False) and not s.tool_allowed("stop_offers", local=True)
    s.restore(Mode.FULL)
    assert s.tool_allowed("finanxe_create_goal", local=False) and s.tool_allowed("delegate_research", local=True)


def test_config_for_mode_gender_and_activation():
    base = {"SUTRA_TOKEN": "t", "ANTHROPIC_API_KEY": "k"}
    cfg = load_config(base, dotenv_path=None)
    assert (cfg.start_mode, cfg.assistant_gender, cfg.activation, cfg.wake_words) == ("full", "feminine", "button", ("hey sutra", "sutra"))
    cfg = load_config({**base, "SUTRA_START_MODE": "limited", "SUTRA_ASSISTANT_GENDER": "neutral", "SUTRA_ACTIVATION": "wake",
                       "SUTRA_WAKE_WORDS": "Hey Jarvis, Jarvis", "SUTRA_LIMITED_TOOLS": "twin_chat, finanxe_x"}, dotenv_path=None)
    assert cfg.start_mode == "limited" and cfg.activation == "wake" and cfg.wake_words == ("hey jarvis", "jarvis")
    assert cfg.limited_tools == ("twin_chat", "finanxe_x")
    for name, bad in (("SUTRA_START_MODE", "turbo"), ("SUTRA_ACTIVATION", "always"), ("SUTRA_ASSISTANT_GENDER", "robot")):
        with pytest.raises(ConfigError):
            load_config({**base, name: bad}, dotenv_path=None)


# ----------------------------------------------------- enforced inside the turn


async def build(tmp_path, script=(), *, results=None, **kw):
    safety = make(tmp_path, **kw)
    gateway = FakeGateway(tools=default_tools(), results=results or {"finanxe_create_goal": pending(), "finanxe_list_debts": SimpleNamespace(kind="ok", text="[]")})
    model = FakeModel([resp(*b) if isinstance(b, tuple) else resp(text(b)) for b in script])
    orch, gateway = await make_orchestrator(model, gateway, safety=safety)
    return orch, gateway, model, safety


async def test_limited_mode_hides_changing_tools_and_refuses_them_if_the_model_asks(tmp_path):
    orch, gateway, model, safety = await build(
        tmp_path, [(tool_use("finanxe_create_goal", {"name": "V"}),), "I can't change things right now.", ("Done.",)]
    )
    safety.lower(Mode.LIMITED)
    reply = await orch.respond("create a goal called V")
    assert reply == "I can't change things right now."
    offered = {t["name"] for t in model.calls[0]["tools"]}
    assert "finanxe_list_debts" in offered and "finanxe_create_goal" not in offered and "delegate_research" not in offered
    assert gateway.calls == []  # the refused call never reached the gateway
    assert "isn't available" in json.dumps(model.calls[1]["messages"])


async def test_a_read_still_works_in_limited_mode(tmp_path):
    orch, gateway, model, safety = await build(tmp_path, [(tool_use("finanxe_list_debts"),), "You have no debts."])
    safety.lower(Mode.LIMITED)
    assert await orch.respond("what debts do I have") == "You have no debts."
    assert gateway.calls_to("finanxe_list_debts") == [{}]


async def test_a_spoken_keyword_drops_a_waiting_action_and_a_later_yes_does_nothing(tmp_path):
    orch, gateway, model, safety = await build(tmp_path, [(tool_use("finanxe_create_goal", {"name": "V"}),), "Shall I go ahead?", "Hello."])
    await orch.respond("create a goal called V")
    assert orch.pending is not None
    assert await orch.respond("safe mode") == LIMITED_REPLY
    assert orch.pending is None and safety.mode is Mode.LIMITED
    await orch.respond("yes")
    assert gateway.calls_to("gateway_confirm") == [] and len(model.calls) == 3
    # The model is told the action was cancelled, so it cannot claim it "may have gone through".
    seen = json.dumps(model.calls[2]["messages"])
    assert "was cancelled. Nothing was done" in seen and "may have gone through" in seen  # the instruction not to say it
    assert "limited mode" in model.calls[2]["system"] and "switch back to full mode" in model.calls[2]["system"]


async def test_lowering_from_the_keyboard_also_cancels_a_waiting_action(tmp_path):
    orch, gateway, model, safety = await build(tmp_path, [(tool_use("finanxe_create_goal", {"name": "V"}),), "Shall I go ahead?"])
    await orch.respond("create a goal called V")
    safety.restore(Mode.LIMITED)  # a key press, not a spoken phrase
    assert await orch.respond("yes") == DROPPED_REPLY
    assert gateway.calls_to("gateway_confirm") == [] and orch.pending is None


async def test_off_answers_one_line_and_no_spoken_phrase_turns_it_back_on(tmp_path):
    orch, gateway, model, safety = await build(tmp_path, ["Never used."])
    assert await orch.respond("go quiet") == OFF_REPLY
    assert await orch.respond("what time is it") == OFF_REPLY
    assert await orch.respond("full mode please, wake up") == OFF_REPLY  # the voice cannot raise it
    assert await orch.respond("मौसम कैसा है") == OFF_REPLY_HI
    assert model.calls == [] and safety.mode is Mode.OFF
    safety.restore(Mode.FULL)
    assert await orch.respond("hello") == "Never used."


async def test_asking_for_full_mode_by_voice_gets_a_pointer_to_the_keyboard(tmp_path):
    orch, *_, safety = await build(tmp_path)
    safety.lower(Mode.LIMITED)
    assert await orch.respond("full mode") == RAISE_REPLY and safety.mode is Mode.LIMITED


async def test_the_distress_phrase_limits_silently_and_the_rest_is_handled_in_limited(tmp_path):
    orch, gateway, model, safety = await build(
        tmp_path, [(tool_use("finanxe_create_goal", {"name": "V"}),), "Shall I go ahead?", (tool_use("finanxe_create_goal", {"name": "V"}),), "Sorry, I can't make changes right now.",
         (tool_use("finanxe_create_goal", {"name": "V"}),), "Still can't."],
        duress_phrase=PHRASE,
    )
    await orch.respond("create a goal called V")
    assert orch.pending is not None
    reply = await orch.respond(f"yes, go ahead, {PHRASE}, thanks")
    assert safety.mode is Mode.LIMITED and orch.pending is None  # dropped, and the yes did not confirm it
    assert gateway.calls_to("gateway_confirm") == [] and gateway.calls_to("finanxe_create_goal") == [{"name": "V"}]  # only the first, held, call
    assert "limited" not in reply.lower() and "safe" not in reply.lower() and "mode" not in reply.lower()  # no announcement
    assert PHRASE not in json.dumps(model.calls[-1]["messages"]).lower()  # the phrase never reaches the model
    system = model.calls[-1]["system"]
    assert "Never mention modes, limits" in system and "switch back to full mode" not in system  # told not to say why
    assert "was cancelled. Nothing was done" in json.dumps(model.calls[-1]["messages"])
    await orch.respond("create a goal called V again")
    assert len(gateway.calls_to("finanxe_create_goal")) == 1  # and a new change cannot even be held


async def test_nothing_unprompted_is_said_and_the_group_chat_stays_closed_in_limited(tmp_path):
    clock = Clock()
    offers = OffersService(OffersStore(tmp_path / "o"), UTC, now=clock)
    sid = offers.add_signal("weather", "Snow soon on the pass", source="w", expires_at=clock() + timedelta(hours=2))
    offers.store.update_signal(sid, status="ready", style="tell", teaser="Heads up, snow is coming.", benefit=1, reason="r", retry_hours=1)
    safety = make(tmp_path)
    offers.arbiter.set_quiet(lambda: not safety.proactive_ok)

    class Group:
        async def ping(self):
            return True

        async def say(self, t):
            return [Line("Priya", "hi")]

        async def reset(self):
            return True

    model = FakeModel([resp(text("It is two."))] * 3)
    orch, _ = await make_orchestrator(model, clock=clock, offers=offers, safety=safety, hangout=HangoutService(Group()))
    assert (await orch.respond("what time is it")).endswith("Heads up, snow is coming.")  # in full mode it is said
    offers.store.update_signal(sid, status="ready")
    orch._open_offer = None
    safety.lower(Mode.LIMITED)
    assert await orch.respond("what time is it") == "It is two."  # in limited it is not
    assert not offers.arbiter.permit("followup", "x", clock()).ok
    assert await orch.respond("catch up with the group") == HANGOUT_LIMITED_REPLY


async def test_idle_research_and_feeds_make_no_request_in_limited(tmp_path):
    r, offers, graph, structured, both, worker, agents, clock, state = make_idle(tmp_path)
    safety = make(tmp_path)
    r.set_quiet(lambda: not safety.proactive_ok)
    safety.lower(Mode.LIMITED)
    assert await r.maybe_run(force=True) == "the assistant is not in full mode"
    assert structured.calls == [] and worker.calls == []
    requests = []

    async def fetch(url):
        requests.append(url)

    feeds = FeedService(offers, None, area="Orem, Utah", news_on=True, news_topics=("cricket",), tz=UTC, fetch=fetch)
    feeds.set_quiet(lambda: not safety.proactive_ok)
    await feeds.poll()
    assert requests == []


async def test_the_tools_that_only_reduce_stay_and_the_prompt_asks_for_the_chosen_gender(tmp_path):
    from sutra_orchestrator.offers import OffersService as O

    safety = make(tmp_path)
    offers = O(OffersStore(tmp_path / "o"), UTC)
    model = FakeModel([resp(text("ok"))])
    orch, _ = await make_orchestrator(model, offers=offers, safety=safety)
    safety.lower(Mode.LIMITED)
    await orch.respond("hello there")
    names = {t["name"] for t in model.calls[0]["tools"]}
    assert "stop_offers" in names  # turning things down is still allowed
    assert "feminine forms" in model.calls[0]["system"]
    for gender, phrase in (("masculine", "masculine forms"), ("neutral", "do not show a gender")):
        m2 = FakeModel([resp(text("ok"))])
        o2, _ = await make_orchestrator(m2, assistant_gender=gender)
        await o2.respond("hi")
        assert phrase in m2.calls[0]["system"]


async def test_commands(tmp_path):
    safety = make(tmp_path)
    cmds = ModeCommands(safety)
    assert (await cmds.handle("/mode", None))[0].startswith("Mode is full")
    assert (await cmds.handle("/mode limited", None))[0].startswith("Mode is now limited") and safety.mode is Mode.LIMITED
    assert (await cmds.handle("/mode full", None))[0].startswith("Mode is now full") and safety.mode is Mode.FULL
    await cmds.handle("/mode off", None)
    assert safety.mode is Mode.OFF
    assert (await cmds.handle("/mode sideways", None))[0] == "Mode commands:"
    assert await cmds.handle("/other", None) is None


# ----------------------------------------------------------------- the wake word


@pytest.mark.parametrize(
    "said,rest",
    [
        ("Hey Sutra, what time is it", "what time is it"), ("sutra", ""), ("Sutra what's the weather?", "what's the weather?"),
        ("ok sootra remind me in five minutes", "remind me in five minutes"), ("hey suitra", ""), ("hi shutra, hello", "hello"),
        ("Hey, Sutra!", ""), ("hay sutra turn it down", "turn it down"),
    ],
)
def test_the_wake_phrase_and_what_follows_it(said, rest):
    assert WakeMatcher().match(said) == rest


@pytest.mark.parametrize(
    "said",
    ["I think sutra is a lovely word", "so anyway the game was great", "hey there how are you", "what does sutra mean", "that's a nice tutor", "", "ok so then sutra said"],
)
def test_other_talk_does_not_wake_it(said):
    assert WakeMatcher().match(said) is None


def test_custom_wake_phrases():
    assert WakeMatcher(("hey jarvis",)).match("Hey Jarvis open the door") == "open the door"
    assert WakeMatcher(("hey jarvis",)).match("hey sutra") is None


class Mic:
    """Hears one scripted clip per start; a clip of None is silence."""

    auto_stop = True

    def __init__(self, clips):
        self.clips = list(clips)
        self.cancelled = False
        self.starts = 0

    def check(self): pass
    def start(self, *, barge_in=False):
        self.starts += 1
        self.cancelled = False
    def wait_done(self, timeout=40.0):
        if not self.clips:
            while not self.cancelled:
                import time; time.sleep(0.01)
    def cancel(self): self.cancelled = True
    def release(self): pass
    def stop(self):
        if self.cancelled or not self.clips:
            return b""
        return self.clips.pop(0) or b""


class Stt:
    def __init__(self, table, fail=None):
        self.table, self.fail, self.heard = table, fail, []

    async def transcribe(self, wav):
        self.heard.append(wav)
        if self.fail:
            raise self.fail
        text_, conf = self.table[wav]
        return Transcript(text_, conf)


class Voice:
    def __init__(self):
        self.said = []

    async def say(self, t):
        self.said.append(t)


class Stop(Exception):
    pass


def wake_session(clips, local_table, cloud_table, *, read=None, local_fail=None):
    mic, local_stt, cloud_stt, voice = Mic(clips), Stt(local_table, local_fail), Stt(cloud_table), Voice()
    cloud = Engines(cloud_stt, voice, "cloud")
    local = Engines(local_stt, voice, "local")
    out = []

    async def never(prompt):
        await asyncio.sleep(3600)

    s = VoiceSession(object(), mic, cloud, local, VoiceSettings(activation="wake"), read=read or never, out=out.append)
    s.attach_wake(WakeMatcher())
    got = {}

    async def fake_conversation(announce=False, carry=None):
        got["carry"] = carry
        raise Stop

    s._conversation = fake_conversation
    return s, mic, local_stt, cloud_stt, voice, out, got


async def test_nothing_reaches_the_cloud_until_the_wake_word_is_heard():
    s, mic, local_stt, cloud_stt, voice, out, got = wake_session(
        [b"a", b"b"],
        {b"a": ("so anyway the game was great", 0.9), b"b": ("hey sutra what time is it", 0.9)},
        {b"b": ("Hey Sutra, what time is it?", 0.95)},
    )
    with pytest.raises(Stop):
        await s._next_command()
    assert local_stt.heard == [b"a", b"b"]  # both heard locally
    assert cloud_stt.heard == [b"b"]  # only after the wake word, and never the chatter before it
    assert got["carry"].text == "what time is it?" and got["carry"].confidence == 0.95


async def test_a_bare_wake_word_gets_a_yes_and_a_normal_listen():
    s, mic, local_stt, cloud_stt, voice, out, got = wake_session([b"b"], {b"b": ("hey sutra", 0.9)}, {})
    with pytest.raises(Stop):
        await s._next_command()
    assert voice.said == ["Yes?"] and got["carry"] is None and cloud_stt.heard == []


async def test_the_button_works_while_listening_for_the_wake_word():
    async def read(prompt):
        await asyncio.sleep(0.05)
        return ""  # Enter

    s, mic, local_stt, cloud_stt, voice, out, got = wake_session([], {}, {}, read=read)
    assert await s._next_command() == "" and s._wake_task is None
    assert cloud_stt.heard == []


async def test_without_a_local_recognizer_it_says_so_and_stays_on_the_button():
    async def read(prompt):
        await asyncio.sleep(0.2)
        return "q"

    s, mic, local_stt, cloud_stt, voice, out, got = wake_session(
        [b"a"], {}, {}, read=read, local_fail=VoiceError("needs faster-whisper")
    )
    assert await s._next_command() == "q"
    assert any("wake word is unavailable" in line.lower() and "Press Enter" in line for line in out) and s._wake is None


async def test_no_listening_for_the_wake_word_when_off_and_keys_set_the_mode(tmp_path):
    safety = make(tmp_path)
    s, mic, *_ = wake_session([b"a"], {b"a": ("hey sutra", 0.9)}, {})
    s.attach_safety(safety)
    safety.restore(Mode.OFF)
    s._ensure_wake()
    assert s._wake_task is None  # off means the microphone is not even opened for the wake word
    keys = iter(["m", "", "s", "", "f", "q"])
    started = []

    async def read(prompt):
        return next(keys)

    s2, mic2, *_rest = wake_session([], {}, {}, read=read)
    s2._wake = None
    s2.attach_safety(make(tmp_path / "k"))

    async def convo(announce=False, carry=None):
        started.append(s2._safety.mode)

    s2._conversation = convo
    await s2.run()
    # m -> off (Enter does nothing), s -> limited (Enter starts a chat), f -> full, then quit
    assert started == [Mode.LIMITED] and s2._safety.mode is Mode.FULL


async def test_proactive_speech_is_withheld_in_limited_and_a_voice_chat_ends_when_switched_off(tmp_path):
    safety = make(tmp_path)
    s, *_ = wake_session([], {}, {})
    s.attach_safety(safety)
    s._offers = SimpleNamespace(ready_notice=lambda: SimpleNamespace(teaser="x"), has_ready=lambda: True)
    s._fg = SimpleNamespace(open_offer=None, pending=None)
    s._interests = SimpleNamespace(next_offer=lambda: object())
    safety.lower(Mode.LIMITED)
    assert not await s._maybe_timely() and not await s._maybe_interest_offer()
    safety.restore(Mode.OFF)
    assert not await s._maybe_offer()
