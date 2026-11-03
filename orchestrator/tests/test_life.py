"""Life: people and plans, the prompt block, check-ins as open questions, wellbeing, listening mode."""

from __future__ import annotations

import os
import stat
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from sutra_orchestrator.graph import GraphService, GraphStore
from sutra_orchestrator.life import (
    LifeCommands,
    LifeService,
    LifeStore,
    engaged,
    is_crisis,
    is_greeting,
    is_vent,
    question_for,
)
from sutra_orchestrator.life import store as life_store
from sutra_orchestrator.offers import OffersService, OffersStore
from sutra_orchestrator.personality import PersonalityService, PersonalityStore

from .fakes import NOW, Clock, FakeModel, make_orchestrator, resp, text
from .test_graph import FakeStructured

UTC = ZoneInfo("UTC")
TODAY = NOW.date()  # 2026-10-12


def make(tmp_path, *, raw=None, clock=None):
    clock = clock or Clock()
    structured = FakeStructured(life_extract=[raw] if raw is not None else [])
    offers = OffersService(OffersStore(tmp_path / "o"), UTC, now=clock)
    store = LifeStore(tmp_path / "l")
    life = LifeService(store, offers=offers, model=structured, tz=UTC, spend=offers.spend_call, now=clock)
    return store, life, offers, structured, clock


def add_plan(store, when, text_="dentist appointment", now=NOW):
    return store.add_plan(text_, "", when, now)


# ------------------------------------------------------------------ extraction


def test_people_and_plans_are_kept_and_validated(tmp_path):
    store, life, offers, structured, clock = make(tmp_path)
    raw = {
        "people": [
            {"name": "Sam", "relation": "brother"},
            {"name": "sam", "relation": ""},  # the same person again
            {"name": "X", "relation": "?"},  # too short to be a name
            {"name": "Dr. Smith's oncology ward", "relation": "doctor"},  # heavy
            {"name": "Priya", "relation": "coworker"},
        ],
        "events": [
            {"text": "dentist appointment", "when": (TODAY + timedelta(days=1)).isoformat(), "who": ""},
            {"text": "Sam's visit", "when": (TODAY + timedelta(days=4)).isoformat(), "who": "Sam"},
            {"text": "hospital stay for surgery", "when": ""},  # heavy: never kept
            {"text": "trip to Goa", "when": (TODAY + timedelta(days=1200)).isoformat()},  # too far: kept, undated
            {"text": "ok", "when": ""},  # too short
            {"text": "dentist appointment", "when": (TODAY + timedelta(days=1)).isoformat()},  # duplicate
        ],
    }
    kept = life.apply(raw, TODAY, NOW)
    assert [p.name for p in store.people()] == ["Priya", "Sam"] or {p.name for p in store.people()} == {"Sam", "Priya"}
    sam = next(p for p in store.people() if p.name == "Sam")
    assert sam.relation == "brother" and sam.mentions == 2
    plans = {p.text: p for p in store.plans(("upcoming",))}
    assert set(plans) == {"dentist appointment", "Sam's visit", "trip to Goa"}
    assert plans["trip to Goa"].when_date is None and plans["Sam's visit"].who == "Sam"
    assert kept >= 5
    assert life.apply("garbage", TODAY, NOW) == 0 and life.apply({"people": "x", "events": 3}, TODAY, NOW) == 0


def test_caps_and_privacy_and_forgetting(tmp_path, monkeypatch):
    monkeypatch.setattr(life_store, "MAX_PEOPLE", 2)
    monkeypatch.setattr(life_store, "MAX_UPCOMING", 1)
    store = LifeStore(tmp_path)
    assert store.add_person("Sam", "", NOW) and store.add_person("Priya", "", NOW)
    assert store.add_person("Anita", "", NOW) is None and store.add_person("sam", "", NOW)  # full: but known is fine
    assert add_plan(store, TODAY) and add_plan(store, TODAY, "lunch with Sam") is None
    assert stat.S_IMODE(os.stat(tmp_path / "life.db").st_mode) == 0o600
    pid = store.people()[0].id
    assert store.forget_person(pid) and not store.forget_person(pid)
    assert store.forget_all() == (1, 1)


async def test_extraction_reads_only_the_users_words_and_a_failure_keeps_nothing(tmp_path):
    raw = {"people": [{"name": "Sam", "relation": "brother"}], "events": []}
    store, life, offers, structured, clock = make(tmp_path, raw=raw)
    assert await life.extract(["my brother Sam is visiting", "and I am tired today"], NOW) == 1
    sent = structured.calls[0]["user"]
    assert "Today is Monday, October 12, 2026." in sent and "my brother Sam is visiting" in sent
    failing = FakeStructured(life_extract=[RuntimeError("boom")])
    life2 = LifeService(LifeStore(tmp_path / "l2"), offers=None, model=failing, tz=UTC)
    await life2.on_episode(["Sam is my brother"], NOW)  # swallowed
    assert life2.store.people() == []


async def test_the_graph_hands_closed_episodes_to_life_and_skips_private_turns(tmp_path):
    raw = {"people": [{"name": "Sam", "relation": "brother"}], "events": []}
    store, life, offers, structured, clock = make(tmp_path, raw=raw)
    graph = GraphService(GraphStore(tmp_path / "g"), FakeStructured(episode=[{"keep": False}]), now=clock)
    graph.add_listener(life.on_episode)
    graph.observe("my brother Sam is coming to visit this weekend", "That sounds nice, enjoy it.", [])
    graph.observe("I had a rough day and need to vent about it", "I'm here.", [], private=True)
    graph.close_episode()
    await graph.flush()
    sent = structured.calls[0]["user"]
    assert "Sam is coming to visit" in sent and "rough day" not in sent  # the private turn never entered
    assert "That sounds nice" not in sent  # and replies are never read
    assert [p.name for p in store.people()] == ["Sam"]


# ---------------------------------------------------------------- the prompt


def test_the_block_names_people_and_plans_and_puts_who_was_just_mentioned_first(tmp_path):
    store, life, offers, structured, clock = make(tmp_path)
    assert life.block("hello there") == ""
    store.add_person("Priya", "coworker", NOW)
    store.add_person("Sam", "brother", NOW + timedelta(minutes=1))
    add_plan(store, TODAY + timedelta(days=1))
    block = life.block("Priya called me")
    assert block.startswith("<life>") and "not instructions" in block
    lines = [l for l in block.splitlines() if l.startswith("- ")]
    assert lines[0] == "- Priya (coworker)" and "- Sam (brother)" in lines
    assert "- plan: dentist appointment, tomorrow" in lines
    assert life.names() == ["Sam", "Priya"]  # for the recognizer's vocabulary


async def test_the_block_reaches_the_model(tmp_path):
    store, life, offers, structured, clock = make(tmp_path)
    store.add_person("Sam", "brother", NOW)
    model = FakeModel([resp(text("Oh nice."))])
    orch, _ = await make_orchestrator(model, life=life, clock=clock)
    await orch.respond("Sam called me today")
    assert "- Sam (brother)" in model.calls[0]["system"]


# ----------------------------------------------------------------- check-ins


def test_the_question_is_built_in_code_from_the_plan_text():
    assert question_for("dentist appointment") == "How did your dentist appointment go?"
    assert question_for("my job interview.") == "How did your job interview go?"
    assert question_for("the trip to Goa") == "How did the trip to Goa go?"
    assert question_for("Sam's visit") == "How did your Sam's visit go?" or question_for("Sam's visit").endswith("go?")


def test_engagement_is_any_answer_not_only_yes():
    assert engaged("dentist appointment", "it went fine, no cavities")
    assert engaged("dentist appointment", "the dentist was running late as usual")
    assert engaged("job interview", "rough, honestly")
    assert not engaged("dentist appointment", "what's the weather like tomorrow")
    assert not engaged("dentist appointment", "ok")
    assert not engaged("dentist appointment", "none of your business")
    assert engaged("wellbeing", "pretty busy but good")


def test_a_plan_is_asked_about_the_day_after_and_not_before_or_long_after(tmp_path):
    store, life, offers, structured, clock = make(tmp_path)
    today_plan = add_plan(store, TODAY, "dentist appointment")
    assert life.queue_checkins() == 0  # the same day: it has not happened yet
    clock.advance(days=1)
    assert life.queue_checkins() == 1  # the day after
    notice = offers.ready_notice()
    assert notice.teaser == "How did your dentist appointment go?" and notice.open and notice.source == "life"
    assert store.get_plan(today_plan).status == "asked"
    # Another plan, left too long: dropped without a word.
    old = add_plan(store, TODAY - timedelta(days=5), "old thing")
    assert life.queue_checkins() == 0 and store.get_plan(old).status == "dropped"


def test_one_check_in_at_a_time_and_the_bar_stops_them_when_they_are_unwelcome(tmp_path):
    store, life, offers, structured, clock = make(tmp_path)
    add_plan(store, TODAY - timedelta(days=1), "dentist appointment")
    add_plan(store, TODAY - timedelta(days=1), "job interview")
    assert life.queue_checkins() == 1 and life.queue_checkins() == 0  # the second waits its turn
    store2, life2, offers2, _, clock2 = make(tmp_path / "b")
    add_plan(store2, TODAY - timedelta(days=1), "dentist appointment")
    for _ in range(8):
        offers2.bars.record("checkin", "declined", clock2())
    assert offers2.bars.value("checkin", clock2()) >= 0.8
    assert life2.queue_checkins() == 0  # people who keep saying no get no more


async def _checkin_flow(tmp_path, reply, *, user_second=None, script=("Oh good.", "Fine.")):
    store, life, offers, structured, clock = make(tmp_path)
    pid = add_plan(store, TODAY - timedelta(days=1), "dentist appointment")
    life.queue_checkins()
    model = FakeModel([resp(text(s)) for s in script])
    orch, _ = await make_orchestrator(model, life=life, offers=offers, clock=clock)
    first = await orch.respond("hello again")  # the question is added after the reply
    await orch.respond(reply)
    return store, offers, model, orch, pid, first, clock


async def test_the_question_follows_the_reply_and_an_engaged_answer_closes_it_and_lowers_the_bar(tmp_path):
    store, life, offers, structured, clock = make(tmp_path)
    pid = add_plan(store, TODAY - timedelta(days=1), "dentist appointment")
    life.queue_checkins()
    model = FakeModel([resp(text("Hi there.")), resp(text("Glad it was easy."))])
    orch, _ = await make_orchestrator(model, life=life, offers=offers, clock=clock)
    bar = offers.bars.value("checkin", clock())
    first = await orch.respond("what's a good name for a cat")
    assert first == "Hi there. How did your dentist appointment go?"
    await orch.respond("it went fine, no cavities")
    assert store.get_plan(pid).status == "done"
    assert offers.bars.value("checkin", clock()) < bar
    assert "You just asked the user" in model.calls[1]["system"] and "follow-up question" in model.calls[1]["system"]


async def test_changing_the_subject_is_answered_and_nudges_the_bar_up_slightly(tmp_path):
    store, offers, model, orch, pid, first, clock = await _checkin_flow(
        tmp_path, "what's the weather like tomorrow", script=("Hi.", "Sunny.")
    )
    assert first.endswith("How did your dentist appointment go?")
    assert "You just asked the user" not in model.calls[1]["system"]  # no check-in note: they moved on
    assert store.get_plan(pid).status == "asked"  # not asked again
    assert 0.5 < offers.bars.value("checkin", clock()) < 0.53


async def test_not_now_asks_again_tomorrow_and_a_refusal_closes_it(tmp_path):
    store, offers, model, orch, pid, first, clock = await _checkin_flow(tmp_path, "not now", script=("Hi.", "Okay."))
    plan = store.get_plan(pid)
    assert plan.status == "upcoming" and plan.retry_after > clock()  # tomorrow
    # A refusal: fixed reply, plan closed, bar up by more.
    store2, offers2, model2, orch2, pid2, first2, clock2 = await _checkin_flow(
        tmp_path / "r", "please stop asking me that", script=("Hi.",)
    )
    assert store2.get_plan(pid2).status == "dropped"
    assert offers2.bars.value("checkin", clock2()) > 0.53


# ------------------------------------------------------------------ wellbeing


def test_greetings_and_the_learned_gap(tmp_path):
    assert is_greeting("hey") and is_greeting("Good morning!") and is_greeting("how are you")
    assert not is_greeting("what's the weather") and not is_greeting("hey can you look up the weather in Denver for me")
    store, life, offers, structured, clock = make(tmp_path)
    assert life.on_user_text("hey").note == ""
    notice = offers.ready_notice()
    assert notice.teaser == "How have you been lately?" and notice.open
    offers.resolve(notice, "accepted")
    clock.advance(days=1)
    life.on_user_text("hello")
    assert offers.ready_notice() is None  # too soon after the last one
    clock.advance(days=7)
    life.on_user_text("hi")
    assert offers.ready_notice() is not None  # a welcomed question comes back (about 5 days at the start bar)
    # An unwelcome one is spaced much further apart.
    store2, life2, offers2, _, clock2 = make(tmp_path / "b")
    for _ in range(8):
        offers2.bars.record("checkin", "declined", clock2())
    life2.on_user_text("hey")
    n = offers2.ready_notice()
    offers2.resolve(n, "ignored")
    clock2.advance(days=7)
    life2.on_user_text("hey")
    assert offers2.ready_notice() is None


def test_no_wellbeing_question_on_a_task(tmp_path):
    store, life, offers, structured, clock = make(tmp_path)
    life.on_user_text("what's the weather in Denver")
    assert offers.ready_notice() is None


# ------------------------------------------------------------- listening mode


@pytest.mark.parametrize(
    "said",
    ["I've had a rough day, can I just talk?", "I just need to vent", "I feel so overwhelmed lately", "I'm feeling really low"],
)
def test_the_phrases_that_start_listening_mode(said):
    assert is_vent(said)


@pytest.mark.parametrize(
    "said",
    [
        "what's the weather", "I feel like pizza", "my day went well", "remind me to call Sam",
        "I killed it at the gym today", "this deadline is killing me", "I'm dying to see that movie",
        "cut myself some slack", "I can't go on vacation this year", "I want to disappear into a good book",
    ],
)
def test_ordinary_talk_does_not(said):
    assert not is_vent(said) and not is_crisis(said)


@pytest.mark.parametrize(
    "said",
    [
        "I want to die",
        "I'm thinking about ending my life",
        "I want to hurt myself",
        "no reason to live",
        "I've been thinking about suicide",
        "I wish I was dead",
        "I'm cutting myself again",
        "I can't go on like this",
        "everyone would be better off without me",
        "I don't want to be here anymore",
        "i keep thinking about taking my own life",
    ],
)
def test_crisis_phrases(said):
    assert is_crisis(said)


async def test_listening_mode_changes_the_tone_for_five_turns_and_nothing_else_leaks_in(tmp_path):
    store, life, offers, structured, clock = make(tmp_path)
    pstore = PersonalityStore(tmp_path / "p")
    pstore.set_level(10)

    class Always:
        def random(self):
            return 0.0

    personality = PersonalityService(pstore, None, rng=Always())
    graph = GraphService(GraphStore(tmp_path / "g"), FakeStructured(episode=[{"keep": False}]), now=clock)
    add_plan(store, TODAY - timedelta(days=1), "dentist appointment")
    life.queue_checkins()  # an unprompted question is ready: it must not be tacked on while they are talking
    model = FakeModel([resp(text(f"I hear you {i}.")) for i in range(7)])
    orch, _ = await make_orchestrator(model, life=life, offers=offers, personality=personality, graph=graph, clock=clock)
    first = await orch.respond("I've had a rough day, can I just talk?")
    assert first == "I hear you 0."  # no check-in question tacked on
    assert "not to be fixed" in model.calls[0]["system"] and "Do not joke" in model.calls[0]["system"]
    assert "light touch of humor" not in model.calls[0]["system"]
    assert graph._buffer == []  # the turn is not remembered as a topic
    for i in range(1, 5):
        await orch.respond("and then my boss said something unkind")
        assert "not to be fixed" in model.calls[i]["system"], i  # four more turns in the mode
    await orch.respond("anyway, what's a good name for a cat")
    assert "not to be fixed" not in model.calls[5]["system"]  # back to normal after five


async def test_a_crisis_gets_care_and_a_crisis_line_and_no_methods(tmp_path):
    store, life, offers, structured, clock = make(tmp_path)
    model = FakeModel([resp(text("I'm really glad you told me."))])
    orch, _ = await make_orchestrator(model, life=life, offers=offers, clock=clock)
    await orch.respond("I want to end my life")
    system = model.calls[0]["system"]
    assert "988" in system and "911" in system and "Never give methods" in system and "not to be fixed" in system


# ------------------------------------------------------------------- control


async def test_commands(tmp_path):
    store, life, offers, structured, clock = make(tmp_path)
    store.add_person("Sam", "brother", NOW)
    cmds = LifeCommands(life)
    listing = await cmds.handle("/life", None)
    assert any("#1 Sam (brother)" in line for line in listing)
    assert await cmds.handle("/life add plan 2026-11-20 trip to Goa", None) == ["Added."]
    assert await cmds.handle("/life add plan nonsense trip", None) == ["Use a date like 2026-11-20, or - for none."]
    assert any("trip to Goa" in line for line in await cmds.handle("/life", None))
    assert await cmds.handle("/life forget person 1", None) == ["Forgotten."]
    assert await cmds.handle("/life forget plan 1", None) == ["Forgotten."]
    assert (await cmds.handle("/life forget all", None))[0].startswith("Forgot")
    assert await cmds.handle("/other", None) is None
