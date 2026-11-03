"""Humor: dials, rules in code, the note's placement, learning from reactions, control."""

from __future__ import annotations

import asyncio
import os
import random
import stat
from collections import Counter

import pytest

from sutra_orchestrator.personality import HumorCommands, PersonalityService, PersonalityStore
from sutra_orchestrator.personality.store import AUTO_LEVEL_MAX, START_SCORE, STYLES

from .fakes import FakeGateway, FakeModel, default_tools, make_orchestrator, pending, resp, text, tool_use
from .test_graph import FakeStructured


class Always:
    """A random source that always passes the chance check (and picks the first style)."""

    def random(self):
        return 0.0


def make(tmp_path, *, level=None, rng=None, model=None):
    store = PersonalityStore(tmp_path)
    if level is not None:
        store.set_level(level)
    return store, PersonalityService(store, model, rng=rng or Always())


def plan_n(service, utterances, **kw):
    return [service.plan(u, **kw) for u in utterances]


# ---------------------------------------------------------------- the profile


def test_defaults_privacy_and_reset(tmp_path):
    store = PersonalityStore(tmp_path)
    assert store.level == 3 and store.variety == 0.7 and store.enabled
    assert store.scores() == START_SCORE and store.scores()["tease"] < store.scores()["dry"]
    assert stat.S_IMODE(os.stat(tmp_path / "personality.db").st_mode) == 0o600
    store.set_level(99)
    assert store.level == 10
    store.set_variety(0.01)
    assert store.variety == 0.2
    store.set_score("dry", 2.0)
    store.reset()
    assert store.level == 3 and store.variety == 0.7 and store.scores() == START_SCORE
    store.close()
    assert PersonalityStore(tmp_path).level == 3  # survives a restart


def test_chance_and_gap_follow_the_level(tmp_path):
    store, service = make(tmp_path, level=3)
    assert service.gap() == 8  # 24 / 3
    store.set_level(10)
    assert service.gap() == 3  # never closer than three turns
    store.set_level(0)
    assert service.plan("tell me a story about trains") is None  # level zero: never


def test_the_chance_is_level_over_twenty_four(tmp_path):
    class Fixed:
        def __init__(self, v):
            self.v = v

        def random(self):
            return self.v

    store, service = make(tmp_path, level=6, rng=Fixed(0.24))  # 6/24 = 0.25
    assert service.plan("what a lovely day for a walk") is not None
    store2, service2 = make(tmp_path / "b", level=6, rng=Fixed(0.26))
    assert service2.plan("what a lovely day for a walk") is None


# ----------------------------------------------------------------- the rules


def test_each_exclusion_blocks_humor(tmp_path):
    cases = [
        dict(action_pending=True),
        dict(has_note=True),
        dict(low_confidence=True),
    ]
    for i, kw in enumerate(cases):
        store, service = make(tmp_path / str(i), level=10)
        assert service.plan("tell me something about pandas", **kw) is None, kw
    store, service = make(tmp_path / "ok", level=10)
    assert service.plan("tell me something about pandas") is not None
    store.set_enabled(False)
    assert plan_n(service, ["more about pandas please", "and bamboo too", "what do they eat then"]) == [None] * 3


@pytest.mark.parametrize(
    "heavy",
    [
        "I'm worried about my debt",
        "my mother died last week",
        "I have to go to the hospital tomorrow",
        "ugh, this is so annoying",
        "my lawyer called about the lawsuit",
        "I'm so stressed about the move",
    ],
)
def test_heavy_topics_and_frustration_keep_it_serious_for_a_few_turns(tmp_path, heavy):
    store, service = make(tmp_path, level=10)
    assert service.plan(heavy) is None
    # The next three turns stay serious even if the new words are harmless.
    assert plan_n(service, ["okay and what about the weather", "what time does the sun set", "and the moon phase"]) == [None] * 3
    # Then it may come back.
    assert service.plan("tell me about the moon landing please") is not None


def test_a_heavy_topic_in_the_recent_turns_also_blocks(tmp_path):
    store, service = make(tmp_path, level=10)
    service.plan("my dog got sick and the doctor says it is serious")
    assert plan_n(service, ["okay, anyway, what about dinner ideas"] * 3) == [None] * 3
    assert service.plan("something light please, what about dessert ideas") is not None


def test_there_is_a_gap_between_offers(tmp_path):
    store, service = make(tmp_path, level=3)  # gap of 8 turns
    first = service.plan("tell me about volcanoes please")
    assert first is not None
    results = plan_n(service, [f"and what about fact number {i}" for i in range(1, 8)])
    assert results == [None] * 7  # seven more turns, still inside the gap
    assert service.plan("one more volcano question for you") is not None


def test_variety_sets_how_much_it_sticks_to_what_works(tmp_path):
    def draw(variety):
        store, service = make(tmp_path / str(variety), rng=random.Random(7))
        store.set_variety(variety)
        store.set_score("absurd", 0.95)
        for s in ("dry", "self", "wordplay", "tease"):
            store.set_score(s, 0.05)
        return Counter(service.choose_style() for _ in range(2000))

    sticky, adventurous = draw(0.2), draw(2.0)
    assert sticky["absurd"] > 1850  # low variety: nearly always the favourite
    assert 0.25 < adventurous["absurd"] / 2000 < 0.5 and len(adventurous) == 5  # high: tries them all


def test_the_note_is_light_optional_and_names_one_style(tmp_path):
    store, service = make(tmp_path, level=10)
    plan = service.plan("tell me about pandas")
    assert plan.style in STYLES and STYLES[plan.style] in plan.note
    assert "only if something natural comes to mind" in plan.note and "One line at most" in plan.note
    assert "Never joke about money, health, family, loss" in plan.note


# --------------------------------------------------------- inside the turn


def system_of(model, n):
    return model.calls[n]["system"]


async def test_the_note_is_on_a_plain_turn(tmp_path):
    store, service = make(tmp_path, level=10)
    model = FakeModel([resp(text("Pandas eat bamboo."))])
    orch, _ = await make_orchestrator(model, personality=service)
    await orch.respond("tell me something about pandas")
    assert "light touch of humor" in system_of(model, 0)


async def test_after_a_tool_call_and_on_the_readback_there_is_no_note(tmp_path):
    store, service = make(tmp_path, level=10)
    gateway = FakeGateway(tools=default_tools(), results={"finanxe_create_goal": pending()})
    model = FakeModel(
        [resp(tool_use("finanxe_create_goal", {"name": "V"})), resp(text("Shall I create goal V? Yes or no?"))]
    )
    orch, _ = await make_orchestrator(model, gateway, personality=service)
    await orch.respond("please create a goal called V")
    assert "light touch of humor" in system_of(model, 0)  # the first step may carry it...
    assert "light touch of humor" not in system_of(model, 1)  # ...the confirmation read-back never does


async def test_a_turn_with_a_pending_action_or_a_fixed_reply_gets_none(tmp_path):
    store, service = make(tmp_path, level=10)
    gateway = FakeGateway(tools=default_tools(), results={"finanxe_create_goal": pending()})
    model = FakeModel(
        [resp(tool_use("finanxe_create_goal", {"name": "V"})), resp(text("Go ahead?")), resp(text("Okay."))]
    )
    orch, _ = await make_orchestrator(model, gateway, personality=service)
    await orch.respond("please create a goal called V")
    service._last_offer_turn = -1000  # clear the gap so only the pending rule can be the reason
    await orch.respond("hmm, what is a goal exactly")  # an action is awaiting: not even asked
    assert all("light touch of humor" not in model.calls[i]["system"] for i in range(2, len(model.calls)))


async def test_with_no_personality_nothing_changes():
    model = FakeModel([resp(text("Plain."))])
    orch, _ = await make_orchestrator(model)
    assert await orch.respond("hi there") == "Plain."
    assert "adjust_humor" not in {t["name"] for t in model.calls[0]["tools"]}


# ------------------------------------------------------------ learning


async def test_a_laugh_raises_the_style_and_a_groan_lowers_it(tmp_path):
    model = FakeStructured(humor_reaction=[
        {"joked": True, "reaction": "laughed"},
        {"joked": True, "reaction": "annoyed"},
        {"joked": False, "reaction": "laughed"},
    ])
    store, service = make(tmp_path, level=10, model=model)
    chat = FakeModel([resp(text(w)) for w in ("one", "two", "three", "four", "five", "six")])
    orch, _ = await make_orchestrator(chat, personality=service)

    async def turn(user):
        service._last_offer_turn = -1000  # let every turn be offered, to test learning only
        await orch.respond(user)
        await orch.flush_graph()

    start = store.scores()["dry"]
    await turn("tell me about pandas")  # humor offered (dry: the rng picks the first style)
    await turn("haha good one")  # the reaction is read on this turn
    assert store.scores()["dry"] == pytest.approx(start + 0.12)
    await turn("tell me about koalas")
    await turn("ugh, not funny")
    assert store.scores()["dry"] == pytest.approx(start + 0.12 - 0.20)
    await turn("tell me about otters")
    await turn("ok thanks")  # no joke was actually made: nothing changes
    assert store.scores()["dry"] == pytest.approx(start + 0.12 - 0.20)


async def test_asking_for_no_more_jokes_sets_the_level_to_zero(tmp_path):
    model = FakeStructured(humor_reaction=[{"joked": True, "reaction": "annoyed", "stop": True}])
    store, service = make(tmp_path, level=5, model=model)
    chat = FakeModel([resp(text("one")), resp(text("two"))])
    orch, _ = await make_orchestrator(chat, personality=service)
    await orch.respond("tell me about pandas")
    await orch.respond("please stop with the jokes")
    await orch.flush_graph()
    assert store.level == 0


async def test_a_failed_check_changes_nothing_and_adds_no_waiting(tmp_path):
    class Slow:
        async def structured(self, **kw):
            await asyncio.sleep(5)

    store, service = make(tmp_path, level=10, model=Slow())
    chat = FakeModel([resp(text("one")), resp(text("two"))])
    orch, _ = await make_orchestrator(chat, personality=service)
    await orch.respond("tell me about pandas")
    started = asyncio.get_event_loop().time()
    await orch.respond("haha")  # the 5-second check runs beside this turn, not before it
    assert asyncio.get_event_loop().time() - started < 1.0
    for t in list(service._tasks):
        t.cancel()
    before = store.scores()
    service2 = PersonalityService(store, FakeStructured(humor_reaction=[RuntimeError("boom")]))
    service2.remember(__import__("sutra_orchestrator.personality", fromlist=["HumorPlan"]).HumorPlan("dry", "n"), "x")
    service2.start_reaction("lol")
    await service2.flush()
    assert store.scores() == before


def test_the_level_drifts_by_one_after_ten_judged_jokes_and_never_far(tmp_path):
    store, _ = make(tmp_path)
    for r in ["laughed"] * 6 + ["neutral"] * 4:
        store.record_reaction("dry", r)
    assert store.level == 4  # six good ones in ten: one step up
    for _ in range(5):
        for r in ["laughed"] * 10:
            store.record_reaction("wordplay", r)
    assert store.level == AUTO_LEVEL_MAX  # by itself it stops at six
    store.set_level(10)
    for r in ["laughed"] * 10:
        store.record_reaction("dry", r)
    assert store.level == 10  # but a level the user set is left alone
    store.set_level(5)
    for r in ["groaned"] * 4 + ["neutral"] * 6:
        store.record_reaction("self", r)
    assert store.level == 4  # four bad ones in ten: one step down


def test_scores_stay_inside_their_bounds(tmp_path):
    store, _ = make(tmp_path)
    for _ in range(30):
        store.record_reaction("dry", "annoyed")
    assert store.scores()["dry"] == 0.05
    for _ in range(30):
        store.record_reaction("dry", "laughed")
    assert store.scores()["dry"] == 0.95


# -------------------------------------------------------------- control


def test_the_tool_changes_the_level_by_voice(tmp_path):
    store, service = make(tmp_path)
    assert [t.name for t in service.tools()] == ["adjust_humor"]
    assert "level 4" in service.adjust("more") and store.level == 4
    assert "level 3" in service.adjust("less") and store.level == 3
    service.adjust("off")
    assert store.level == 0
    service.adjust("on")
    assert store.level == 3  # back to where it was
    assert service.adjust("sideways") == "No change was made."


async def test_the_model_can_adjust_humor_through_the_tool(tmp_path):
    store, service = make(tmp_path)
    model = FakeModel([resp(tool_use("adjust_humor", {"change": "more"})), resp(text("Sure, a bit more."))])
    orch, _ = await make_orchestrator(model, personality=service)
    assert await orch.respond("be a bit funnier") == "Sure, a bit more."
    assert store.level == 4


async def test_commands(tmp_path):
    store, service = make(tmp_path)
    cmds = HumorCommands(service)
    shown = await cmds.handle("/humor", None)
    assert "level 3 of 10" in shown[0] and any(line.strip().startswith("dry") for line in shown)
    assert (await cmds.handle("/humor level 6", None))[0] == "Level is 6 of 10."
    assert "0.30" in (await cmds.handle("/humor variety 0.3", None))[0]
    assert (await cmds.handle("/humor style tease 0.9", None))[0] == "tease is now 0.90."
    assert (await cmds.handle("/humor level lots", None)) == ["That needs a number."]
    assert (await cmds.handle("/humor off", None)) == ["Humor is off."] and not store.enabled
    await cmds.handle("/humor on", None)
    assert store.enabled
    await cmds.handle("/humor reset", None)
    assert store.level == 3 and store.scores() == START_SCORE
    assert await cmds.handle("/other", None) is None
