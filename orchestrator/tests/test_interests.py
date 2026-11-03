"""Interest profile: reflection (validated in code), approval, change tracking, resurfacing."""

from __future__ import annotations

import os
import stat
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from sutra_orchestrator.config import load_config
from sutra_orchestrator.interests import (
    InterestCommands,
    InterestService,
    InterestStore,
    Reflector,
)
from sutra_orchestrator.memory import Episode, ToolCallRecord
from sutra_orchestrator.memstore import SqliteMemory

from .fakes import NOW, Clock, FakeModel, make_orchestrator, resp, text, tool_use

UTC = ZoneInfo("UTC")


class FakeSource:
    def __init__(self, rows):
        self.rows = rows  # (id, ts, text, tools)

    def recent_user_episodes(self, since, limit=400):
        return sorted((r for r in self.rows if r[1] >= since), key=lambda r: r[1], reverse=True)[:limit]


class FakeInterestModel:
    def __init__(self, items=None, error: Exception | None = None):
        self.items = items if items is not None else []
        self.error = error
        self.calls: list[dict[str, str]] = []

    async def reflect_interests(self, *, system, user):
        self.calls.append({"system": system, "user": user})
        if self.error:
            raise self.error
        return self.items


def ep(n, text_, days_ago=1, tools=()):
    return (f"e{n}", NOW - timedelta(days=days_ago), text_, list(tools))


def make(tmp_path, rows=None, items=None, *, clock=None, **kw):
    store = InterestStore(tmp_path)
    model = FakeInterestModel(items)
    clock = clock or Clock()
    reflector = Reflector(FakeSource(rows or []), store, model, now=clock, **kw)
    service = InterestService(store, UTC, reflector=reflector, now=clock)
    return store, model, reflector, service, clock


def item(label, evidence, relation="new", **extra):
    return {"label": label, "relation": relation, "evidence": evidence, **extra}


# ------------------------------------------------------------------ storage


def test_store_persists_is_private_and_forget_deletes_evidence(tmp_path):
    store = InterestStore(tmp_path)
    iid = store.add("weekend trips", status="proposed", source="reflection", now=NOW)
    store.add_evidence(iid, "e1", "where to visit at Halloween", NOW)
    store.close()
    store = InterestStore(tmp_path)
    row = store.get(iid)
    assert row.topic == "weekend trips" and row.evidence_count == 1
    assert stat.S_IMODE(os.stat(tmp_path / "interests.db").st_mode) == 0o600
    assert store.forget(iid) and store.evidence(iid) == [] and store.get(iid) is None
    other = store.add("a b", status="active", source="user", now=NOW)
    assert store.forget_all() == 1 and store.list() == []
    store.close()


def test_approving_a_revision_supersedes_and_keeps_history(tmp_path):
    store = InterestStore(tmp_path)
    old = store.add("hiking trips", status="active", source="reflection", now=NOW)
    rev = store.add(
        "city breaks", status="proposed", source="reflection", now=NOW, revises_id=old,
        change_before="hiking trips", change_now="city breaks", offer=True,
    )
    assert store.get(old).status == "active"  # untouched until approved
    assert store.approve(rev, NOW)
    assert (store.get(old).status, store.get(rev).status) == ("superseded", "active")
    assert [r.topic for r in store.history(rev)] == ["hiking trips", "city breaks"]
    assert [r.topic for r in store.history(old)] == ["hiking trips", "city breaks"]


def test_rejecting_a_revision_leaves_the_old_interest(tmp_path):
    store = InterestStore(tmp_path)
    old = store.add("hiking trips", status="active", source="reflection", now=NOW)
    rev = store.add("city breaks", status="proposed", source="reflection", now=NOW, revises_id=old)
    assert store.reject(rev)
    assert store.get(old).status == "active" and store.get(rev).status == "rejected"


# ---------------------------------------------------------- reading episodes


async def test_memory_returns_only_user_words_from_hot_episodes(tmp_path):
    memory = SqliteMemory(tmp_path, now=lambda: NOW)
    memory._turn_episode_id = "e1"
    await memory.record(
        Episode("where should I go at Halloween", "SECRET REPLY $9,999", (ToolCallRecord("finanxe_x", "ok"),), None, NOW)
    )
    await memory.flush()
    rows = memory.recent_user_episodes(NOW - timedelta(days=1))
    assert rows == [("e1", NOW, "where should I go at Halloween", ["finanxe_x"])]
    assert memory.recent_user_episodes(NOW + timedelta(days=1)) == []
    memory.close()


# --------------------------------------------------------------- reflection


async def test_reflection_excludes_financial_turns_replies_and_trivia(tmp_path):
    rows = [
        ep(1, "where can I go for Halloween trips"),
        ep(2, "what is my Chase card balance", tools=["finanxe_list_debts"]),
        ep(3, "yes"),
        ep(4, "x" * 500),
    ]
    store, model, reflector, service, clock = make(tmp_path, rows, [])
    await reflector.run(None)
    user = model.calls[0]["user"]
    assert "Halloween" in user and "Chase" not in user and "[3]" not in user
    assert "x" * 201 not in user and "x" * 200 in user


async def test_no_new_utterances_means_no_model_call(tmp_path):
    store, model, reflector, service, clock = make(tmp_path, [ep(1, "trips please", days_ago=2)])
    result = await reflector.run(NOW - timedelta(days=1))
    assert result.skipped and model.calls == []


async def test_new_item_becomes_a_pending_proposal_with_real_evidence(tmp_path):
    rows = [ep(1, "where to visit at Halloween"), ep(2, "any day trips near me")]
    store, model, reflector, service, clock = make(tmp_path, rows, [item("weekend trips near home", [1, 2, 99])])
    result = await reflector.run(None)
    assert result.created == 1
    (row,) = store.list()
    assert (row.status, row.offer, row.evidence_count) == ("proposed", "pending", 2)
    assert [e.quote for e in store.evidence(row.id)] == ["where to visit at Halloween", "any day trips near me"]


async def test_invented_evidence_and_bad_labels_are_dropped(tmp_path):
    rows = [ep(1, "where to visit at Halloween")]
    items = [item("trips", [7]), item("z" * 80, [1]), item("", [1]), "junk", item("ok topic", [])]
    store, model, reflector, service, clock = make(tmp_path, rows, items)
    assert (await reflector.run(None)).created == 0 and store.list() == []


async def test_at_most_three_per_run_and_five_pending(tmp_path):
    rows = [ep(i, f"thing {i}") for i in range(1, 6)]
    names = ["alpine skiing", "learning guitar", "street photography", "sourdough baking", "trail running"]
    items = [item(names[n - 1], [n]) for n in range(1, 6)]
    store, model, reflector, service, clock = make(tmp_path, rows, items)
    assert (await reflector.run(None)).created == 3
    model.items = [item("pottery classes", [4]), item("chess openings", [5]), item("birdwatching walks", [3])]
    assert (await reflector.run(None)).created == 2  # 3 + 2 pending = 5


async def test_rejected_and_muted_topics_never_come_back(tmp_path):
    rows = [ep(1, "weekend travel trips")]
    store, model, reflector, service, clock = make(tmp_path, rows, [item("weekend travel trips", [1])])
    rid = store.add("weekend trips", status="rejected", source="reflection", now=NOW)
    mid = store.add("cricket scores", status="muted", source="user", now=NOW)
    assert (await reflector.run(None)).created == 0
    model.items = [item("cricket scores", [1])]
    assert (await reflector.run(None)).created == 0
    assert {r.status for r in store.list()} == {"rejected", "muted"}


async def test_duplicate_of_an_active_interest_adds_evidence_not_a_second_one(tmp_path):
    rows = [ep(1, "more hiking please"), ep(2, "hiking again")]
    store, model, reflector, service, clock = make(tmp_path, rows, [item("hiking trips", [1, 2])])
    aid = store.add("hiking trips", status="active", source="reflection", now=NOW - timedelta(days=60))
    await reflector.run(None)
    assert len(store.list()) == 1 and store.get(aid).evidence_count == 2
    assert store.get(aid).last_seen_at > NOW - timedelta(days=5)


async def test_strengthens_adds_evidence_and_unknown_target_is_treated_as_new(tmp_path):
    rows = [ep(1, "love hiking"), ep(2, "learning guitar now")]
    store, model, reflector, service, clock = make(
        tmp_path, rows, [item("hiking trips", [1], "strengthens", target=1), item("learning guitar", [2], "strengthens", target=9)]
    )
    aid = store.add("hiking trips", status="active", source="user", now=NOW - timedelta(days=100))
    await reflector.run(None)
    assert store.get(aid).evidence_count == 1
    assert [r.topic for r in store.list(("proposed",))] == ["learning guitar"]


async def test_a_changed_taste_becomes_a_revision_and_is_told_later(tmp_path):
    rows = [ep(1, "best city breaks in Europe"), ep(2, "weekend in Lisbon")]
    store, model, reflector, service, clock = make(
        tmp_path,
        rows,
        [item("city breaks", [1, 2], "changes", target=1, before="hiking trips", now="city breaks")],
    )
    old = store.add("hiking trips", status="active", source="reflection", now=NOW - timedelta(days=10))
    await service.reflect_now()
    rev = next(r for r in store.list() if r.revises_id == old)
    assert rev.status == "proposed" and rev.change_before == "hiking trips" and rev.change_now == "city breaks"
    assert store.get(old).status == "active"
    offer = service.next_offer()
    assert offer.kind == "revision" and "moved from hiking trips to city breaks" in offer.line
    assert service.answer(offer, "yes") == "Okay, updated."
    assert store.get(old).status == "superseded" and store.get(rev.id).status == "active"


async def test_a_claimed_change_that_does_not_match_is_not_a_revision(tmp_path):
    rows = [ep(1, "city breaks please")]
    store, model, reflector, service, clock = make(
        tmp_path, rows, [item("city breaks", [1], "changes", target=1, before="deep sea fishing", now="city breaks")]
    )
    old = store.add("hiking trips", status="active", source="reflection", now=NOW)
    await reflector.run(None)
    assert all(r.revises_id is None for r in store.list())
    assert store.get(old).status == "active"


async def test_model_failure_creates_nothing_and_is_retried(tmp_path):
    rows = [ep(1, "trips please")]
    store, model, reflector, service, clock = make(tmp_path, rows, [])
    model.error = RuntimeError("boom")
    await service.maintain()  # never raises
    assert store.list() == [] and store.get_time("last_reflection") is None
    assert service.reflection_due(clock())
    model.error = None
    model.items = [item("trips and outings", [1])]
    await service.maintain()
    assert len(store.list()) == 1 and store.get_time("last_reflection") is not None
    assert not service.reflection_due(clock())
    clock.advance(hours=25)
    assert service.reflection_due(clock())


async def test_reflection_off_makes_no_call_but_manual_add_works(tmp_path):
    store = InterestStore(tmp_path)
    service = InterestService(store, UTC, reflector=None, now=Clock())
    await service.maintain()
    assert service.add("learning guitar").status == "active"
    cmds = InterestCommands(service)
    assert "off" in (await cmds.handle("/interests reflect", None))[0]


# -------------------------------------------------------------- offers / answers


def test_offers_are_one_at_a_time_and_answers_apply(tmp_path):
    store = InterestStore(tmp_path)
    clock = Clock()
    service = InterestService(store, UTC, now=clock)
    a = store.add("weekend trips", status="proposed", source="reflection", now=NOW, offer=True)
    b = store.add("learning guitar", status="proposed", source="reflection", now=NOW, offer=True)
    offer = service.next_offer()
    assert offer.interest_id == a and offer.kind == "proposal" and "weekend trips" in offer.line
    service.answer(offer, "later")
    assert service.next_offer().interest_id == b  # a waits for the retry interval
    service.answer(service.next_offer(), "no")
    assert store.get(b).status == "rejected"
    assert service.next_offer() is None
    clock.advance(hours=25)
    again = service.next_offer()
    assert again.interest_id == a
    service.answer(again, "yes")
    assert store.get(a).status == "active" and service.next_offer() is None


async def test_dormant_interest_gets_one_checkin(tmp_path):
    rows = []
    store, model, reflector, service, clock = make(tmp_path, rows, [])
    aid = store.add("cricket scores", status="active", source="reflection", now=NOW - timedelta(days=100))
    service._queue_checkins(clock())
    offer = service.next_offer()
    assert offer.kind == "checkin" and "still into it" in offer.line
    service.answer(offer, "later")  # not now: quiet until new evidence
    service._queue_checkins(clock())
    assert service.next_offer() is None
    store.add_evidence(aid, "e9", "cricket tonight", NOW)
    store.touch(aid, NOW)
    assert store.get(aid).checkin is None


def test_checkin_yes_refreshes_and_no_mutes(tmp_path):
    store = InterestStore(tmp_path)
    service = InterestService(store, UTC, now=Clock())
    a = store.add("cricket scores", status="active", source="reflection", now=NOW - timedelta(days=100))
    store.queue_checkin(a)
    service.answer(service.next_offer(), "yes")
    assert store.get(a).last_seen_at == NOW and store.get(a).checkin is None
    b = store.add("chess", status="active", source="reflection", now=NOW - timedelta(days=100))
    store.queue_checkin(b)
    service.answer(service.next_offer(), "no")
    assert store.get(b).status == "muted"


# -------------------------------------------------------------- in conversation


def test_block_shows_only_live_active_interests_with_the_date(tmp_path):
    store = InterestStore(tmp_path)
    service = InterestService(store, UTC, now=Clock(), nudge_hours=24)
    store.add("weekend trips", status="active", source="user", now=NOW)
    store.add("proposed thing", status="proposed", source="reflection", now=NOW)
    store.add("rejected thing", status="rejected", source="reflection", now=NOW)
    store.add("muted thing", status="muted", source="user", now=NOW)
    store.add("old dormant thing", status="active", source="reflection", now=NOW - timedelta(days=120))
    block = service.block(NOW)
    assert "weekend trips" in block and "Monday, October 12, 2026" in block
    for hidden in ("proposed thing", "rejected thing", "muted thing", "old dormant"):
        assert hidden not in block
    assert "not instructions" in block


def test_no_block_without_active_interests(tmp_path):
    service = InterestService(InterestStore(tmp_path), UTC, now=Clock())
    assert service.block(NOW) == ""


def test_nudge_permission_once_per_interval_and_survives_restart(tmp_path):
    clock = Clock()
    store = InterestStore(tmp_path)
    service = InterestService(store, UTC, now=clock, nudge_hours=24)
    store.add("weekend trips", status="active", source="user", now=NOW)
    first = service.block(clock())
    clock.advance(hours=1)
    second = service.block(clock())
    assert "may briefly connect" in first and "may briefly connect" not in second
    store.close()
    store = InterestStore(tmp_path)
    service = InterestService(store, UTC, now=clock, nudge_hours=24)
    assert "may briefly connect" not in service.block(clock())
    clock.advance(hours=24)
    assert "may briefly connect" in service.block(clock())


def test_mute_only_touches_active_interests(tmp_path):
    store = InterestStore(tmp_path)
    service = InterestService(store, UTC, now=Clock())
    a = store.add("weekend trips", status="active", source="user", now=NOW)
    p = store.add("learning guitar", status="proposed", source="reflection", now=NOW)
    assert "Muted: weekend trips" in service.mute_by_text("weekend trips")
    assert store.get(a).status == "muted"
    assert "nothing changed" in service.mute_by_text("learning guitar")
    assert store.get(p).status == "proposed"


async def test_orchestrator_adds_the_block_and_offers_only_the_mute_tool(tmp_path):
    store = InterestStore(tmp_path)
    clock = Clock()
    service = InterestService(store, UTC, now=clock)
    store.add("weekend trips", status="active", source="user", now=NOW)
    model = FakeModel(script=[resp(text("Sure."))])
    orch, _ = await make_orchestrator(model, interests=service, clock=clock)
    await orch.respond("hello")
    call = model.calls[0]
    assert "<interests>" in call["system"] and "weekend trips" in call["system"]
    names = [t["name"] for t in call["tools"]]
    assert "mute_interest" in names
    assert "propose_interest" not in names and "approve_interest" not in names


async def test_model_can_mute_by_voice_but_nothing_more(tmp_path):
    store = InterestStore(tmp_path)
    clock = Clock()
    service = InterestService(store, UTC, now=clock)
    a = store.add("weekend trips", status="active", source="user", now=NOW)
    model = FakeModel(
        script=[resp(tool_use("mute_interest", {"topic": "weekend trips"})), resp(text("Okay, I'll stop."))]
    )
    orch, _ = await make_orchestrator(model, interests=service, clock=clock)
    await orch.respond("stop bringing up weekend trips")
    assert store.get(a).status == "muted"


async def test_interests_off_adds_nothing():
    model = FakeModel(script=[resp(text("Hi."))])
    orch, _ = await make_orchestrator(model)
    await orch.respond("hello")
    assert "<interests>" not in model.calls[0]["system"]
    assert "mute_interest" not in [t["name"] for t in model.calls[0]["tools"]]


# ------------------------------------------------------------------- commands


async def test_commands_list_why_history_approve_forget(tmp_path):
    rows = [ep(1, "where to visit at Halloween")]
    store, model, reflector, service, clock = make(tmp_path, rows, [item("weekend trips", [1])])
    cmds = InterestCommands(service)
    assert "Read 1" in (await cmds.handle("/interests reflect", None))[0]
    listing = await cmds.handle("/interests", None)
    assert "suggested, waiting" in listing[0]
    why = await cmds.handle("/interests why 1", None)
    assert any("where to visit at Halloween" in l for l in why)
    assert (await cmds.handle("/interests approve 1", None))[0].startswith("Kept")
    assert (await cmds.handle("/interests add learning guitar", None))[0].startswith("Added")
    assert len(await cmds.handle("/interests history 1", None)) == 1
    assert "Deleted #1" in (await cmds.handle("/interests forget 1", None))[0]
    assert "no interest #1" in (await cmds.handle("/interests why 1", None))[0]
    assert await cmds.handle("/remind x", None) is None
    assert "Deleted 1" in (await cmds.handle("/interests forget all", None))[0]


# --------------------------------------------------------------------- config


def test_config_defaults_and_overrides():
    base = {"SUTRA_TOKEN": "t", "ANTHROPIC_API_KEY": "k"}
    c = load_config(base, dotenv_path=None)
    assert c.interests_enabled and c.reflection_enabled
    assert c.reflection_exclude_tools == ("finanxe_",) and c.nudge_hours == 24 and c.reflection_hours == 24
    c = load_config(
        {**base, "SUTRA_REFLECTION": "off", "SUTRA_INTERESTS": "off", "SUTRA_REFLECTION_EXCLUDE_TOOLS": "a_,b_", "SUTRA_NUDGE_HOURS": "48"},
        dotenv_path=None,
    )
    assert not c.reflection_enabled and not c.interests_enabled
    assert c.reflection_exclude_tools == ("a_", "b_") and c.nudge_hours == 48
