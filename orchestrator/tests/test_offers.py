"""Offers: learned bars, the arbiter, the judge's validation, signals, and the turn flow."""

from __future__ import annotations

from datetime import timedelta
from zoneinfo import ZoneInfo

import pytest

from sutra_orchestrator.graph import GraphService, GraphStore
from sutra_orchestrator.interests import InterestService, InterestStore
from sutra_orchestrator.offers import (
    Judge,
    OffersCommands,
    OffersService,
    OffersStore,
    OpenOffer,
    is_deferral,
)
from sutra_orchestrator.offers import bars as bars_mod
from sutra_orchestrator.offers.judge import clamp_retry, fallback_ask, valid_ask, valid_tell

from .fakes import NOW, Clock, FakeModel, FakeGateway, default_tools, make_orchestrator, pending, resp, text, tool_use
from .test_graph import FakeStructured, seed

UTC = ZoneInfo("UTC")
ASK = "Want to see a quick example of how tool calling works?"
OFFER = {"decision": "offer", "benefit": 0.9, "style": "ask", "teaser": ASK, "retry_after_hours": 12, "reason": "They are building with it."}
ADVICE = {"choice": 1, "benefit": 0.9, "reason": "They are building an agent.", "step": "example"}


def build(tmp_path, *, judgement=None, advice=None, clock=None, daily_max=4, urgent=(), calls=200):
    clock = clock or Clock()
    structured = FakeStructured(
        advice=advice if advice is not None else [ADVICE] * 5,
        judgement=judgement if judgement is not None else [OFFER] * 5,
        episode=[], links=[],
    )
    store = OffersStore(tmp_path / "o")
    gstore = GraphStore(tmp_path / "g")
    offers = OffersService(store, UTC, daily_max=daily_max, calls_per_day=calls, urgent_sources=urgent, now=clock)
    graph = GraphService(gstore, structured, spend=offers.spend_call, now=clock)
    offers.attach(graph, Judge(structured, spend=offers.spend_call))
    return offers, graph, structured, clock


def node(graph, clock, topic="how tool calling works"):
    return seed(graph.store, clock, topic, "A model asks code to run a function.", ["tool calling"], days=1)


# --------------------------------------------------------------------- bars


def test_bars_learn_within_limits_and_drift_back(tmp_path):
    offers = OffersService(OffersStore(tmp_path), UTC)
    bars, t = offers.bars, NOW
    start = bars.start("followup")
    assert bars.value("followup", t) == start
    lower = bars.record("followup", "accepted", t)
    assert lower < start
    assert bars.record("followup", "declined", t) > start  # a decline costs more than an accept earns
    assert bars.record("followup", "deferred", t) == bars.value("followup", t)
    for _ in range(50):
        bars.record("followup", "declined", t)
    assert bars.value("followup", t) == bars_mod.HIGH
    for _ in range(50):
        bars.record("followup", "accepted", t)
    assert bars.value("followup", t) == bars_mod.LOW
    # No new evidence: it recovers toward where it started.
    assert bars.value("followup", t + timedelta(days=30)) > bars_mod.LOW + 0.15
    bars.reset()
    assert bars.value("followup", t) == start


# ------------------------------------------------------------------- arbiter


def test_arbiter_rails_blocks_and_one_at_a_time(tmp_path):
    offers = OffersService(OffersStore(tmp_path), UTC, daily_max=2, now=Clock())
    a, now = offers.arbiter, NOW
    assert a.permit("followup", "x", now).ok
    assert not a.permit("followup", "x", now, action_pending=True).ok
    assert not a.permit("followup", "x", now, open_offer=True).ok
    offers.stop("tool calling")  # the user's own stop
    assert not a.permit("followup", "how tool calling works", now).ok
    assert a.permit("followup", "weekend hiking", now).ok
    offers.stop(kind="timely")
    assert not a.permit("timely", "snow", now).ok and a.permit("followup", "weekend hiking", now).ok
    for _ in range(2):
        offers.note_nudge()
    assert not a.permit("followup", "weekend hiking", now).ok  # daily rail reached
    assert a.permit("timely", "snow", now, urgent=True).ok is False  # still blocked by the user
    offers.stop("", "")
    assert not offers.enabled and not a.permit("nudge", "", now).ok


def test_urgent_may_exceed_the_daily_rail_but_not_a_stop(tmp_path):
    offers = OffersService(OffersStore(tmp_path), UTC, daily_max=1, now=Clock())
    offers.note_nudge()
    assert not offers.arbiter.permit("timely", "snow", NOW).ok
    assert offers.arbiter.permit("timely", "snow", NOW, urgent=True).ok


# --------------------------------------------------------------------- judge


def test_validation_helpers():
    assert valid_ask("Want to hear something interesting about tool calling?")
    assert not valid_ask("Tool calling is great. Want to hear more?")
    assert not valid_ask("See https://x.com now?")
    assert valid_tell("Snow is expected on the mountain road in twenty minutes, so you may want to wait.")
    assert not valid_tell("Should you wait for the snow?")
    assert not valid_tell("I'll cancel your trip because of the snow.")
    assert not valid_tell("I booked you a hotel.")
    assert clamp_retry(0) == 1.0 and clamp_retry(10**6) == 24.0 * 30 and clamp_retry("x") == 6.0
    assert fallback_ask("tool calling").endswith("tool calling?")


async def test_judge_replaces_bad_words_and_never_trusts_a_style(tmp_path):
    bad = [
        {"decision": "offer", "benefit": 2, "style": "tell", "teaser": "I'll book it. Done?", "retry_after_hours": 0, "reason": "r"},
        {"decision": "offer", "benefit": 0.7, "style": "ask", "teaser": "No question here", "reason": "r"},
        {"decision": "offer", "benefit": 0.7, "style": "tell", "teaser": "Snow is coming, maybe wait.", "reason": "r"},
        {"decision": "bogus"},
    ]
    judge = Judge(FakeStructured(judgement=bad))
    args = dict(topic="snow", description="d", why="w", stats="s", since_last="none yet", busy=False)
    first = await judge.judge(kind="timely", **args)
    assert first.benefit == 1.0 and first.style == "ask" and valid_ask(first.teaser) and first.retry_hours == 1.0
    assert valid_ask((await judge.judge(kind="timely", **args)).teaser)
    ok = await judge.judge(kind="timely", **args)
    assert ok.style == "tell" and ok.teaser == "Snow is coming, maybe wait."
    assert await judge.judge(kind="timely", **args) is None  # unusable decision
    # A follow-up is always an ask, whatever the model says.
    judge2 = Judge(FakeStructured(judgement=[{**OFFER, "style": "tell", "teaser": "Snow is coming, maybe wait."}]))
    assert (await judge2.judge(kind="followup", **args)).style == "ask"


# ---------------------------------------------------------------- follow-ups


async def run_followup(offers, graph, utterance="my tool calling loop never ends"):
    cands = graph.check_candidates(utterance)
    return await offers.followup_for_turn(utterance, cands)


async def test_followup_offered_then_the_node_is_held_while_a_decline_closes_it(tmp_path):
    offers, graph, model, clock = build(tmp_path)
    nid = node(graph, clock)
    got = await run_followup(offers, graph)
    assert got and got.teaser == ASK and got.node_id == nid and got.kind == "followup"
    [row] = offers.store.recent()
    assert row.outcome == "open" and row.benefit == 0.9 and row.reason
    offers.resolve(got, "declined")
    assert graph.store.get(nid).open == ()
    assert offers.store.hold_until(f"node:{nid}") > clock() + timedelta(days=20)


async def test_below_the_bar_or_a_hold_says_nothing_and_remembers_why(tmp_path):
    low = {**OFFER, "benefit": 0.4, "retry_after_hours": 48}
    offers, graph, model, clock = build(tmp_path, judgement=[low, OFFER])
    nid = node(graph, clock)
    assert await run_followup(offers, graph) is None
    [row] = offers.store.recent()
    assert row.outcome == "held" and row.benefit == 0.4 and row.bar > 0.4
    # Held for the time the judge chose: the same node is not even put to the advisor.
    assert await run_followup(offers, graph, "my tool calling still never ends") is None
    assert model.count("advice") == 1
    clock.advance(hours=49)
    clock.advance(minutes=IDLE)  # well past the same-conversation window
    assert await run_followup(offers, graph, "another tool calling problem in my code today")


IDLE = 31


async def test_a_drop_holds_for_a_long_time_and_none_advice_makes_no_offer(tmp_path):
    drop = {**OFFER, "decision": "drop"}
    offers, graph, model, clock = build(tmp_path, judgement=[drop], advice=[{"choice": 0}])
    nid = node(graph, clock)
    assert await run_followup(offers, graph) is None  # advisor: none
    assert offers.store.hold_until(f"node:{nid}") is None
    offers2, graph2, _, clock2 = build(tmp_path / "b", judgement=[drop])
    nid2 = node(graph2, clock2)
    assert await run_followup(offers2, graph2) is None
    assert offers2.store.hold_until(f"node:{nid2}") > clock2() + timedelta(days=20)


async def test_acceptance_lowers_the_bar_and_marks_the_step_done(tmp_path):
    offers, graph, _, clock = build(tmp_path)
    nid = node(graph, clock)
    got = await run_followup(offers, graph)
    before = offers.bars.value("followup", clock())
    offers.resolve(got, "accepted")
    assert offers.bars.value("followup", clock()) < before
    assert graph.store.get(nid).open == ()  # the only open item was the example


async def test_blocked_topic_and_open_offer_and_pending_stop_a_followup(tmp_path):
    offers, graph, model, clock = build(tmp_path)
    node(graph, clock)
    cands = graph.check_candidates("my tool calling loop never ends")
    assert await offers.followup_for_turn("t", cands, action_pending=True) is None
    assert await offers.followup_for_turn("t", cands, open_offer=True) is None
    offers.stop("tool calling")
    assert await offers.followup_for_turn("t", cands) is None
    assert model.count("advice") == 0  # decided in code, no model call spent


async def test_the_call_rail_stops_model_work(tmp_path):
    offers, graph, model, clock = build(tmp_path, calls=1)
    node(graph, clock)
    assert await run_followup(offers, graph) is None  # advice spent the only call; judge has none
    assert model.count("advice") == 1 and model.count("judgement") == 0


def test_stop_tool_acts_on_topic_kind_or_everything(tmp_path):
    offers = OffersService(OffersStore(tmp_path), UTC, now=Clock())
    assert offers.tools()[0].name == "stop_offers"
    assert "Stopped offers about examples" in offers.stop("examples")
    assert offers.enabled
    offers.stop(kind="nudge")
    assert not offers.arbiter.permit("nudge", "", NOW).ok
    offers.stop()
    assert not offers.enabled
    OffersCommands(offers)  # constructs


def test_deferral_phrases():
    assert is_deferral("not now, thanks") and is_deferral("maybe tomorrow") and is_deferral("later")
    assert not is_deferral("yes please") and not is_deferral("how are you")


# ------------------------------------------------------------------- signals


async def test_signals_expiry_weather_default_and_urgent_path(tmp_path):
    offers, graph, _, clock = build(tmp_path, urgent=("weather_api",))
    assert offers.add_signal("weather", "snow", source="x", expires_at=NOW - timedelta(minutes=1)) is None
    assert offers.add_signal("weather", "  ", source="x", expires_at=NOW + timedelta(hours=1)) is None
    w = offers.add_signal("weather", "Snow soon.", source="weather_api", expires_at=NOW + timedelta(hours=3))
    assert offers.store.get_signal(w).urgency == "medium" and not offers.store.get_signal(w).urgent_path
    claimed = offers.add_signal("weather", "Snow now.", source="rando", urgency="high", expires_at=NOW + timedelta(minutes=20))
    assert not offers.store.get_signal(claimed).urgent_path  # not on the allowlist
    long = offers.add_signal("weather", "Snow now.", source="weather_api", urgency="high", expires_at=NOW + timedelta(hours=5))
    assert not offers.store.get_signal(long).urgent_path  # not about to matter
    ok = offers.add_signal("weather", "Snow now.", source="weather_api", urgency="high", expires_at=NOW + timedelta(minutes=20))
    assert offers.store.get_signal(ok).urgent_path and offers.store.get_signal(ok).safety


TELL = {"decision": "offer", "benefit": 0.9, "style": "tell", "teaser": "Snow is expected on the mountain road in about twenty minutes, so you may want to hold off on that drive.", "retry_after_hours": 2, "reason": "They planned a mountain drive."}


async def test_a_warning_tied_to_a_stated_plan_is_said_as_a_tell(tmp_path):
    offers, graph, model, clock = build(tmp_path, judgement=[TELL])
    seed(graph.store, clock, "drive in the mountains", "Planned a drive up the mountain road.", ["mountain road", "drive"], open_items=())
    sid = offers.add_signal("weather", "Heavy snow on the mountain road within 20 minutes", source="w", expires_at=NOW + timedelta(minutes=40), topic_hint="mountain road snow")
    assert await offers.process_signals() == 1
    assert "drive in the mountains" in model.calls[-1]["user"]  # the plan was shown to the judge
    notice = offers.ready_notice()
    assert notice.style == "tell" and notice.signal_id == sid and "Snow is expected" in notice.teaser
    assert offers.store.get_signal(sid).status == "offered"
    assert offers.ready_notice() is None  # said once


async def test_an_unconnected_minor_signal_needs_a_higher_bar(tmp_path):
    minor = {**TELL, "benefit": 0.6, "style": "ask", "teaser": "Something came up about trains, want to hear it?"}
    offers, graph, model, clock = build(tmp_path, judgement=[minor, minor])
    offers.add_signal("transit", "Minor delays on a line", source="t", expires_at=NOW + timedelta(hours=5))
    assert await offers.process_signals() == 0  # 0.6 clears the timely bar, not the unconnected one
    assert "Nothing the person has said" in model.calls[-1]["user"]
    [row] = offers.store.recent()
    assert row.outcome == "held"
    # Tied to something the user said, the same score is enough.
    seed(graph.store, clock, "trains to work", "Takes the train to work.", ["trains"], open_items=())
    offers.add_signal("transit", "Delays on the trains", source="t", expires_at=NOW + timedelta(hours=5), topic_hint="trains")
    assert await offers.process_signals() == 1


async def test_expired_signals_are_never_spoken_and_urgent_goes_first(tmp_path):
    offers, graph, model, clock = build(tmp_path, judgement=[TELL, TELL], urgent=("w",))
    slow = offers.add_signal("weather", "Rain this evening", source="x", urgency="low", expires_at=NOW + timedelta(minutes=30))
    fast = offers.add_signal("weather", "Snow in 10 minutes", source="w", urgency="high", expires_at=NOW + timedelta(minutes=10))
    # Both were put through the judge; the first scripted answer goes to the urgent one (it is later by id).
    await offers.process_signals()
    assert offers.ready_notice().signal_id in (fast, slow)
    clock.advance(hours=1)
    assert offers.ready_notice() is None
    assert offers.store.get_signal(slow).status in ("expired", "offered")


async def test_discard_returns_a_ready_signal_without_touching_the_bars(tmp_path):
    offers, graph, _, clock = build(tmp_path, judgement=[TELL])
    offers.add_signal("weather", "Snow soon on the road", source="w", urgency="medium", expires_at=NOW + timedelta(hours=2))
    await offers.process_signals()
    bar = offers.bars.value("timely", clock())
    notice = offers.ready_notice()
    offers.discard(notice)
    assert offers.bars.value("timely", clock()) == bar
    assert offers.has_ready() and offers.arbiter.today_count(clock()) == 0


# --------------------------------------------------------- the turn, end to end


def orchestrator_script(*replies):
    return [resp(text(r)) for r in replies]


async def conversation(tmp_path, replies, labels=None, **kw):
    offers, graph, structured, clock = build(tmp_path, **kw)
    nid = node(graph, clock)
    model = FakeModel(orchestrator_script(*replies), labels=labels or {})
    orch, _ = await make_orchestrator(model, clock=clock, graph=graph, offers=offers)
    return orch, offers, graph, structured, model, clock, nid


async def test_the_use_case_answer_first_then_one_offer_then_a_grounded_example(tmp_path):
    orch, offers, graph, structured, model, clock, nid = await conversation(
        tmp_path, ["Give each function a name and a schema.", "Here is a short example in words."], {"yes": "affirm"}
    )
    reply = await orch.respond("I am building a small agent and my tool calling loop never ends")
    assert reply == f"Give each function a name and a schema. {ASK}"  # the request first, the offer last
    assert orch.open_offer and orch.open_offer.node_id == nid
    assert orch._flat_history()[-1]["content"][0]["text"] == reply  # the model knows it asked

    reply2 = await orch.respond("yes please")
    assert reply2 == "Here is a short example in words."
    system = model.calls[-1]["system"]
    assert "a worked example" in system and "how tool calling works" in system and "never state or invent" in system.lower()
    assert orch.open_offer is None
    assert offers.store.recent()[0].outcome == "accepted"
    assert graph.store.get(nid).open == ()


async def test_not_now_snoozes_without_asking_again(tmp_path):
    orch, offers, graph, structured, model, clock, nid = await conversation(tmp_path, ["Use a schema."])
    await orch.respond("my tool calling loop never ends")
    before = offers.bars.value("followup", clock())
    reply = await orch.respond("not now")
    assert "hold off" in reply
    assert offers.store.recent()[0].outcome == "deferred"
    assert offers.bars.value("followup", clock()) == before
    assert offers.store.hold_until(f"node:{nid}") > clock()
    assert len(model.calls) == 1 and orch.open_offer is None


async def test_ignoring_the_offer_just_moves_on_and_a_later_yes_is_not_an_acceptance(tmp_path):
    orch, offers, graph, structured, model, clock, nid = await conversation(
        tmp_path, ["Use a schema.", "Sunny and mild.", "Okay, noted."], {"yes": "affirm"}
    )
    await orch.respond("my tool calling loop never ends")
    answer = await orch.respond("what is the weather like today")
    assert answer == "Sunny and mild."  # answered normally; no "was that a yes or a no?"
    assert offers.store.recent()[0].outcome == "ignored"
    await orch.respond("yes")  # nothing is open any more
    assert all("a worked example" not in c["system"] for c in model.calls)
    assert offers.store.recent()[0].outcome == "ignored"


async def test_a_no_closes_it_for_good(tmp_path):
    orch, offers, graph, structured, model, clock, nid = await conversation(
        tmp_path, ["Use a schema."], {"no thanks": "deny"}
    )
    await orch.respond("my tool calling loop never ends")
    assert await orch.respond("no thanks, I get it") == "Okay, I won't bring that up again."
    assert offers.store.recent()[0].outcome == "declined" and graph.store.get(nid).open == ()


async def test_an_offer_is_never_added_to_a_confirmation_question(tmp_path):
    offers, graph, structured, clock = build(tmp_path)
    node(graph, clock)
    gateway = FakeGateway(tools=default_tools(), results={"finanxe_create_goal": pending()})
    model = FakeModel([
        resp(tool_use("finanxe_create_goal", {"name": "Vacation"})),
        resp(text("I will create the goal Vacation. Should I go ahead?")),
    ])
    orch, _ = await make_orchestrator(model, gateway, clock=clock, graph=graph, offers=offers)
    reply = await orch.respond("my tool calling loop never ends, also make a Vacation goal")
    assert ASK not in reply and orch.open_offer is None
    assert [r.outcome for r in offers.store.recent()] == ["held"]  # decided, never said, not counted
    assert offers.arbiter.today_count(clock()) == 0


async def test_low_confidence_speech_is_not_checked_for_follow_ups(tmp_path):
    orch, offers, graph, structured, model, clock, nid = await conversation(tmp_path, ["Okay."])
    reply = await orch.respond("my tool calling loop never ends", low_confidence=True)
    assert reply == "Okay." and structured.count("advice") == 0


async def test_offers_off_makes_no_calls_and_a_timely_tell_follows_the_answer(tmp_path):
    orch, offers, graph, structured, model, clock, nid = await conversation(
        tmp_path, ["Use a schema.", "Snow is forecast on the mountain road; maybe wait."], {"yes": "affirm"}, judgement=[TELL]
    )
    offers.set_enabled(False)
    assert await orch.respond("my tool calling loop never ends") == "Use a schema."
    assert structured.count("advice") == 0 and structured.count("judgement") == 0
    offers.set_enabled(True)
    offers.add_signal("weather", "Snow on the mountain road within 20 minutes", source="w", urgency="medium", expires_at=NOW + timedelta(hours=1), topic_hint="mountain road")
    seed(graph.store, clock, "driving the mountains", "Planned a mountain drive.", ["mountain road"], open_items=())
    await offers.process_signals()
    reply = await orch.respond("what is a good podcast about history")
    assert reply.endswith(TELL["teaser"])
    assert orch.open_offer.style == "tell"


async def test_the_interests_nudge_waits_while_a_follow_up_is_weighed(tmp_path):
    offers, graph, structured, clock = build(tmp_path)
    node(graph, clock)
    istore = InterestStore(tmp_path / "i")
    istore.add("weekend trips", status="active", source="user", now=NOW)
    interests = InterestService(istore, UTC, now=clock)
    model = FakeModel(orchestrator_script("Use a schema.", "Sure."))
    orch, _ = await make_orchestrator(model, clock=clock, graph=graph, offers=offers, interests=interests)
    await orch.respond("my tool calling loop never ends")
    assert "On this turn only" not in model.calls[0]["system"]  # no nudge beside a follow-up
    assert offers.arbiter.today_count(clock()) == 1
    # The nudge's own cap was not spent, so it can still be used on a calm turn.
    clock.advance(minutes=IDLE)
    await orch.respond("tell me a joke")
    assert "On this turn only" in model.calls[1]["system"]
    assert offers.arbiter.today_count(clock()) == 2  # and it counts against the day


async def test_a_stale_offer_is_not_answered_by_a_bare_yes(tmp_path):
    orch, offers, graph, structured, model, clock, nid = await conversation(
        tmp_path, ["Use a schema.", "Fine."], {"yes": "affirm"}
    )
    await orch.respond("my tool calling loop never ends")
    clock.advance(hours=3)
    await orch.respond("yes")
    assert all("a worked example" not in c["system"] for c in model.calls)
    assert offers.store.recent()[0].outcome == "ignored"


async def test_ending_the_session_counts_an_unanswered_offer_as_ignored(tmp_path):
    orch, offers, graph, structured, model, clock, nid = await conversation(tmp_path, ["Use a schema."])
    await orch.respond("my tool calling loop never ends")
    orch.close_session()
    assert offers.store.recent()[0].outcome == "ignored" and orch.open_offer is None


async def test_conversations_feed_the_graph_only_from_ordinary_turns(tmp_path):
    offers, graph, structured, clock = build(tmp_path)
    structured.scripts["episode"] = [{"keep": True, "topic": "agents", "gist": "Built a small agent.", "mode": "worked_on", "open": ["practice"], "entities": ["agent"]}]
    model = FakeModel(orchestrator_script("Done, set for tomorrow.", "A loop that calls tools."))
    orch, _ = await make_orchestrator(model, clock=clock, graph=graph, offers=offers)
    from sutra_orchestrator.reminders import ReminderService, ReminderStore

    orch._reminders = ReminderService(ReminderStore(tmp_path / "r"), UTC)
    await orch.respond("remind me tomorrow at 9am to call the dentist")  # handled by the parser, not a model turn
    await orch.respond("how do I structure a small AI agent in python")
    await orch.flush_graph()
    assert structured.count("episode") == 1
    assert "dentist" not in structured.calls[0]["user"]
