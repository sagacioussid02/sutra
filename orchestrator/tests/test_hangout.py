"""Gossip hangout: a clearly fictional group chat the user steps into, kept apart from the assistant."""

from __future__ import annotations

import asyncio
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

import pytest

from sutra_orchestrator.config import load_config
from sutra_orchestrator.errors import ConfigError
from sutra_orchestrator.graph import GraphService, GraphStore
from sutra_orchestrator.hangout import (
    ENTRY,
    LEFT,
    UNREACHABLE,
    WITHHELD,
    HangoutCommands,
    HangoutReply,
    HangoutService,
    HttpGroupClient,
    Line,
    check_url,
    is_start,
    is_stop,
    lines_from,
    parse_voices,
)
from sutra_orchestrator.life import LifeService, LifeStore
from sutra_orchestrator.memory import NullMemory
from sutra_orchestrator.offers import OffersService, OffersStore
from sutra_orchestrator.personality import PersonalityService, PersonalityStore
from sutra_orchestrator.voice.loop import VoiceSession, VoiceSettings
from sutra_orchestrator.voice.openai_engines import OpenAISpeaker
from sutra_orchestrator.voice.types import Engines
from zoneinfo import ZoneInfo

from .fakes import Clock, FakeModel, make_orchestrator, resp, text
from .test_graph import FakeStructured

# ----------------------------------------------------------------- the phrases


@pytest.mark.parametrize(
    "said",
    ["let's catch up with the group", "talk to the group", "hang out with Priya", "open the group chat", "gossip time", "put me in the group chat", "chat with Ananya"],
)
def test_start_phrases(said):
    assert is_start(said) and not is_stop(said)


@pytest.mark.parametrize("said", ["leave the group", "back to Sutra", "exit hangout", "bye everyone", "close the group chat"])
def test_stop_phrases(said):
    assert is_stop(said) and not is_start(said)


@pytest.mark.parametrize("said", ["what's the weather", "tell me about group theory", "my group of friends is great"])
def test_ordinary_talk_does_not_start_it(said):
    assert not is_start(said)


# -------------------------------------------------------------- parsing, config


def test_replies_are_cleaned_capped_and_the_user_is_left_out():
    data = {"events": [
        {"speaker": "You", "kind": "user", "text": "hi everyone"},
        {"speaker": "Priya", "kind": "social", "text": "omg  hi!!\x00\x07 how are you"},
        {"speaker": "Rahul", "kind": "social", "text": "x" * 900},
        {"speaker": "Info Agent", "kind": "info", "text": "Weather in Ranchi: sunny"},
        {"speaker": "", "kind": "social", "text": "nameless"},
        "garbage",
    ] + [{"speaker": "Ananya", "kind": "social", "text": f"line {i}"} for i in range(10)]}
    lines = lines_from(data)
    assert lines[0] == Line("Priya", "omg hi!! how are you") and len(lines[1].text) == 400
    assert lines[2].speaker == "Info Agent" and len(lines) == 6
    assert lines_from({"events": "no"}) == [] and lines_from(None) == []


def test_only_a_local_address_is_allowed_and_voices_can_be_overridden():
    assert check_url("http://127.0.0.1:8765/") == "http://127.0.0.1:8765"
    assert check_url("http://localhost:9000") == "http://localhost:9000"
    for bad in ("http://example.com", "http://10.0.0.5:8765", "file:///etc/passwd", "ftp://127.0.0.1"):
        with pytest.raises(ValueError):
            check_url(bad)
    assert parse_voices("")["Priya"] == "nova"
    v = parse_voices("Priya=shimmer, Rahul = ash ,bogus")
    assert v["Priya"] == "shimmer" and v["Rahul"] == "ash" and v["Ananya"] == "sage"
    cfg = load_config({"SUTRA_TOKEN": "t", "ANTHROPIC_API_KEY": "k", "SUTRA_GOSSIP_URL": "http://127.0.0.1:8765/"}, dotenv_path=None)
    assert cfg.gossip_url == "http://127.0.0.1:8765"
    assert load_config({"SUTRA_TOKEN": "t", "ANTHROPIC_API_KEY": "k"}, dotenv_path=None).gossip_url == ""
    with pytest.raises(ConfigError):
        load_config({"SUTRA_TOKEN": "t", "ANTHROPIC_API_KEY": "k", "SUTRA_GOSSIP_URL": "http://example.com"}, dotenv_path=None)


# ------------------------------------------------- the client over a real socket


class FakeApp(BaseHTTPRequestHandler):
    """A tiny stand-in for the gossip app's REST API."""

    log: list = []

    def log_message(self, *a):
        pass

    def _send(self, payload, status=200):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self._send({"messages": [], "state": {}}) if self.path == "/api/state" else self._send({"error": "x"}, 404)

    def do_POST(self):
        raw = self.rfile.read(int(self.headers.get("Content-Length", "0"))).decode() or "{}"
        FakeApp.log.append((self.path, json.loads(raw)))
        if self.path == "/api/message":
            said = json.loads(raw)["text"]
            self._send({"events": [
                {"speaker": "You", "kind": "user", "text": said},
                {"speaker": "Priya", "kind": "social", "text": "ooh tell me more"},
                {"speaker": "Rahul", "kind": "social", "text": "hm. source?"},
            ], "state": {}, "reward": 1})
        elif self.path == "/api/reset":
            self._send({"messages": [], "state": {}})
        else:
            self._send({"error": "x"}, 404)


@pytest.fixture
def app():
    FakeApp.log = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), FakeApp)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


async def test_the_client_talks_to_the_app_and_sends_the_text_verbatim(app):
    client = HttpGroupClient(app)
    assert await client.ping()
    lines = await client.say("I think Tina and Vijay are getting married")
    assert [l.speaker for l in lines] == ["Priya", "Rahul"]
    assert FakeApp.log[-1] == ("/api/message", {"text": "I think Tina and Vijay are getting married"})
    assert await client.reset() and FakeApp.log[-1][0] == "/api/reset"


async def test_an_app_that_is_not_running_is_a_plain_failure():
    client = HttpGroupClient("http://127.0.0.1:9", timeout=1.0)  # nothing listens here
    assert not await client.ping() and not await client.reset()
    assert await HangoutService(client).send("hello") == UNREACHABLE


# ------------------------------------------------------------ inside Sutra


class Group:
    """An in-memory group: records exactly what it was sent."""

    def __init__(self, up=True):
        self.up = up
        self.sent: list[str] = []
        self.resets = 0

    async def ping(self):
        return self.up

    async def say(self, said):
        self.sent.append(said)
        return [Line("Priya", f"priya reacts to {said[:12]}"), Line("Rahul", "rahul is dry")]

    async def reset(self):
        self.resets += 1
        return True


async def make(tmp_path, group, *, script=(), with_extras=True):
    clock = Clock()
    extras = {}
    if with_extras:
        offers = OffersService(OffersStore(tmp_path / "o"), ZoneInfo("UTC"), now=clock)
        sid = offers.add_signal("weather", "Snow soon on the pass", source="w", expires_at=clock() + __import__("datetime").timedelta(hours=2))
        offers.store.update_signal(sid, status="ready", style="tell", teaser="Heads up, snow.", benefit=1, reason="r", retry_hours=1)
        graph = GraphService(GraphStore(tmp_path / "g"), FakeStructured(), now=clock)
        life = LifeService(LifeStore(tmp_path / "l"), offers=offers, model=None, tz=ZoneInfo("UTC"), now=clock)
        pstore = PersonalityStore(tmp_path / "p")
        pstore.set_level(10)

        class Always:
            def random(self):
                return 0.0

        extras = dict(offers=offers, graph=graph, life=life, personality=PersonalityService(pstore, None, rng=Always()))
    model = FakeModel([resp(text(s)) for s in script])

    class CountingMemory(NullMemory):
        def __init__(self):
            self.recorded = []

        async def record(self, episode):
            self.recorded.append(episode)

    memory = CountingMemory()
    orch, _ = await make_orchestrator(
        model, memory=memory, clock=clock, hangout=HangoutService(group), **extras
    )
    return orch, model, memory, extras


async def test_entering_says_what_it_is_and_the_users_words_go_through_untouched(tmp_path):
    group = Group()
    orch, model, memory, extras = await make(tmp_path, group)
    assert await orch.respond("let's catch up with the group") == ENTRY
    assert "fictional friends" in ENTRY and "separate app" in ENTRY and "look up public facts online" in ENTRY
    reply = await orch.respond("I saw Tina talking to Vijay yesterday")
    assert group.sent == ["I saw Tina talking to Vijay yesterday"]  # exactly what was said
    assert isinstance(reply, HangoutReply) and reply.splitlines()[0].startswith("Priya: priya reacts to")
    assert [l.speaker for l in reply.lines] == ["Priya", "Rahul"] and reply.voices["Priya"] == "nova"
    assert model.calls == []  # no model composed, summarized or answered anything


async def test_money_health_and_family_trouble_stay_out_of_the_group(tmp_path):
    group = Group()
    orch, *_ = await make(tmp_path, group)
    await orch.respond("catch up with the group")
    for private in ("I'm worried about my debt", "my mother is in the hospital", "my divorce is getting messy"):
        assert await orch.respond(private) == WITHHELD
    assert group.sent == []


async def test_distress_ends_the_mode_and_sutra_listens(tmp_path):
    group = Group()
    orch, model, *_ = await make(tmp_path, group, script=["I'm really glad you told me.", "Hi, I'm here."])
    await orch.respond("catch up with the group")
    reply = await orch.respond("I want to end my life")
    assert reply == "I'm really glad you told me." and group.sent == []  # never sent to the group
    assert "988" in model.calls[0]["system"]  # the crisis note
    assert not orch._hangout_on
    assert await orch.respond("hello again") != ""  # and the next message is Sutra's, not the group's
    assert group.sent == []


async def test_nothing_from_the_group_reaches_history_memory_the_graph_or_any_prompt(tmp_path):
    group = Group()
    orch, model, memory, extras = await make(tmp_path, group, script=["I don't know what you mean."])
    await orch.respond("hang out with Priya")
    await orch.respond("Priya is adding masala again lol")
    await orch.respond("what do you think about Rahul")  # still the group's, not Sutra's
    assert orch._flat_history() == [] and memory.recorded == []
    assert extras["graph"]._buffer == []
    assert extras["offers"].has_ready()  # a heads-up was waiting, and was not tacked on to a group reply
    assert extras["personality"]._awaiting is None
    assert await orch.respond("leave the group") == LEFT
    await orch.respond("what did Priya say?")
    sent_to_model = json.dumps(model.calls[0]["messages"]) + model.calls[0]["system"]
    assert "priya reacts" not in sent_to_model and "rahul is dry" not in sent_to_model and "masala" not in sent_to_model


async def test_it_is_not_reachable_or_not_configured_or_a_held_action_blocks_it(tmp_path):
    down = Group(up=False)
    orch, model, *_ = await make(tmp_path, down)
    assert await orch.respond("catch up with the group") == UNREACHABLE and not orch._hangout_on
    # Not configured at all: the phrase is an ordinary message for the model.
    model2 = FakeModel([resp(text("Which group do you mean?"))])
    orch2, _ = await make_orchestrator(model2)
    assert await orch2.respond("catch up with the group") == "Which group do you mean?"


async def test_it_and_interpreter_mode_end_each_other_and_the_session_ends_both(tmp_path):
    group = Group()
    orch, model, *_ = await make(tmp_path, group, script=["नमस्ते"], with_extras=False)
    await orch.respond("catch up with the group")
    assert orch._hangout_on
    await orch.respond("be my interpreter between English and Hindi")
    assert orch._interpreting and not orch._hangout_on
    await orch.respond("hang out with the group")
    assert orch._hangout_on and not orch._interpreting
    orch.close_session()
    assert not orch._hangout_on


async def test_text_mode_still_works_after_leaving(tmp_path):
    group = Group()
    orch, model, *_ = await make(tmp_path, group, script=["It is sunny."], with_extras=False)
    await orch.respond("gossip time")
    await orch.respond("leave the group")
    assert await orch.respond("what's the weather") == "It is sunny."


# ------------------------------------------------------------------ voices


class Voiced:
    def __init__(self):
        self.said = []

    async def say(self, text_, voice=None):
        self.said.append((voice, text_))
        await asyncio.sleep(0)


class Plain:
    def __init__(self):
        self.said = []

    async def say(self, text_):
        self.said.append(text_)


def reply_of(*pairs):
    reply = HangoutReply("\n".join(f"{w}: {t}" for w, t in pairs))
    reply.lines = [Line(w, t) for w, t in pairs]
    reply.voices = parse_voices("")
    return reply


def session(speaker):
    engines = Engines(SimpleNamespace(), speaker, "cloud")
    return VoiceSession(object(), SimpleNamespace(auto_stop=True), engines, engines, VoiceSettings(), read=None, out=lambda s: None)


async def test_each_friend_is_spoken_in_their_own_voice():
    spk = Voiced()
    s = session(spk)
    await s._say_group(reply_of(("Priya", "omg hi"), ("Rahul", "hm"), ("Ananya", "hello"), ("Info Agent", "sunny")))
    assert spk.said == [("nova", "omg hi"), ("onyx", "hm"), ("sage", "hello"), ("echo", "sunny")]


async def test_a_speaker_that_cannot_change_voice_says_who_is_talking():
    spk = Plain()
    s = session(spk)
    await s._say_group(reply_of(("Priya", "omg hi"), ("Rahul", "hm")))
    assert spk.said == ["Priya says: omg hi", "Rahul says: hm"]


async def test_speaking_over_the_group_stops_the_remaining_lines():
    class Cut(Voiced):
        pass

    spk = Cut()
    s = session(spk)
    calls = []

    async def fake_say_reply(text_, voice=None):
        calls.append(text_)
        s._last_cut = len(calls) == 1  # the user cuts in on the first line
        return "interruption"

    s._say_reply = fake_say_reply
    heard = await s._say_group(reply_of(("Priya", "one"), ("Rahul", "two"), ("Ananya", "three")))
    assert heard == "interruption" and calls == ["one"]


async def test_the_cloud_voice_takes_a_per_call_voice_and_caches_by_voice():
    created, played = [], []

    class Stream:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def iter_bytes(self, size):
            yield b"\x01\x00"

    class Speech:
        class with_streaming_response:  # noqa: N801
            @staticmethod
            def create(**kw):
                created.append(kw["voice"])
                return Stream()

    async def play(chunks):
        played.append(b"".join([c async for c in chunks]))

    speaker = OpenAISpeaker("k", voice="coral", client=SimpleNamespace(audio=SimpleNamespace(speech=Speech())), play=play)
    await speaker.say("omg hi", voice="nova")
    await speaker.say("omg hi", voice="nova")  # cached
    await speaker.say("omg hi", voice="onyx")  # same words, another voice: not the same audio
    await speaker.say("omg hi")  # the default voice
    assert created == ["nova", "onyx", "coral"]


# ---------------------------------------------------------------- control


async def test_commands(tmp_path):
    group = Group()
    cmds = HangoutCommands(HangoutService(group), "http://127.0.0.1:8765")
    status = await cmds.handle("/hangout", None)
    assert status[0] == "Group app at http://127.0.0.1:8765: answering."
    assert await cmds.handle("/hangout reset", None) == ["The group's world was reset."] and group.resets == 1
    group.up = False
    assert "not answering" in (await cmds.handle("/hangout", None))[0]
    assert await cmds.handle("/other", None) is None
