"""Reminders: the deterministic parser, the store, the scheduler, the
REPL commands, and the orchestrator's "remind me" hook.

No model is involved in any of these paths; the orchestrator tests use a
FakeModel with an empty script, so any model call would fail loudly.
"""

from __future__ import annotations

import asyncio
import os
import stat
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from sutra_orchestrator.__main__ import watch_task
from sutra_orchestrator.config import load_config
from sutra_orchestrator.errors import ConfigError
from sutra_orchestrator.reminders import (
    ReminderScheduler,
    ReminderService,
    ReminderStore,
    parse_request,
    reminder_request,
)
from sutra_orchestrator.reminders.commands import ReminderCommands

from .fakes import NOW, Clock, FakeModel, make_orchestrator, resp, text

UTC = ZoneInfo("UTC")
DENVER = ZoneInfo("America/Denver")


def parse(request: str, now: datetime = NOW, tz: ZoneInfo = UTC):
    return parse_request(request, now, tz)


# --------------------------------------------------------------------- parser


def test_reminder_request_detection():
    assert reminder_request("Remind me in 20 minutes to call Sam") == "in 20 minutes to call Sam"
    assert reminder_request("  remind me at 5pm to stretch") == "at 5pm to stretch"
    assert reminder_request("what do I owe?") is None
    assert reminder_request("remind Sam to call me") is None  # not "remind me"


def test_parse_relative_minutes_and_hours():
    got = parse("in 20 minutes to call Sam")
    assert got is not None and got.text == "call Sam"
    assert got.fire_at == NOW + timedelta(minutes=20)

    got = parse("in 2 hours water the plants")
    assert got is not None and got.text == "water the plants"
    assert got.fire_at == NOW + timedelta(hours=2)

    got = parse("in an hour to stretch")
    assert got is not None and got.fire_at == NOW + timedelta(hours=1)

    got = parse("in half an hour to stretch")
    assert got is not None and got.fire_at == NOW + timedelta(minutes=30)


def test_parse_at_clock_time_today_and_rollover():
    got = parse("at 5pm to take the bins out")
    assert got is not None and got.text == "take the bins out"
    assert got.fire_at == datetime(2026, 10, 12, 17, 0, tzinfo=timezone.utc)

    # 9am has already passed at noon, so a bare "at" means tomorrow.
    got = parse("at 9am to water the plants")
    assert got is not None
    assert got.fire_at == datetime(2026, 10, 13, 9, 0, tzinfo=timezone.utc)

    got = parse("at 17:30 to call Sam")
    assert got is not None
    assert got.fire_at == datetime(2026, 10, 12, 17, 30, tzinfo=timezone.utc)

    got = parse("at noon to eat lunch")
    assert got is not None
    assert got.fire_at == datetime(2026, 10, 13, 12, 0, tzinfo=timezone.utc)


def test_parse_tomorrow_and_today():
    got = parse("tomorrow at 9am to water the plants")
    assert got is not None
    assert got.fire_at == datetime(2026, 10, 13, 9, 0, tzinfo=timezone.utc)

    got = parse("today at 5pm to stretch")
    assert got is not None
    assert got.fire_at == datetime(2026, 10, 12, 17, 0, tzinfo=timezone.utc)

    # "today at" a time that has passed must not silently become tomorrow.
    assert parse("today at 9am to stretch") is None


def test_parse_rejects_anything_it_cannot_pin_down():
    for bad in (
        "",
        "sometime to do stuff",
        "whenever to do stuff",
        "at five to do stuff",
        "at 5 to do stuff",  # bare hour: am or pm would be a guess
        "at 25:00 to do stuff",
        "at 13:99 to do stuff",
        "in 0 minutes to do stuff",
        "in a while to do stuff",
        "next week to do stuff",
        "in 20 minutes",  # a time but nothing to remind about
        "at 5pm",
        "tomorrow at 9am",
    ):
        assert parse(bad) is None, bad


def test_parse_dst_spring_forward():
    # US spring forward 2026: clocks jump 2:00 -> 3:00 on March 8 in Denver.
    now = datetime(2026, 3, 7, 12, 0, tzinfo=DENVER)
    assert now.utcoffset() == timedelta(hours=-7)  # MST

    got = parse_request("tomorrow at 9am to spring forward", now, DENVER)
    assert got is not None
    # 9am on March 8 is MDT (UTC-6) = 15:00 UTC.
    assert got.fire_at.utcoffset() == timedelta(hours=-6)
    assert got.fire_at.astimezone(timezone.utc) == datetime(
        2026, 3, 8, 15, 0, tzinfo=timezone.utc
    )

    # "in 24 hours" is 24 elapsed hours, not 24 wall-clock hours: it lands
    # at 13:00 MDT on March 8, not 12:00.
    got = parse_request("in 24 hours to check the clock", now, DENVER)
    assert got is not None
    # Compare in UTC: subtracting two datetimes that share one tzinfo does
    # wall-clock arithmetic in Python and would hide the offset change.
    elapsed = got.fire_at.astimezone(timezone.utc) - now.astimezone(timezone.utc)
    assert elapsed == timedelta(hours=24)
    assert got.fire_at.hour == 13


# ---------------------------------------------------------------------- store


def make_store(tmp_path) -> ReminderStore:
    return ReminderStore(tmp_path / "data")


def seed(store: ReminderStore, fire_at: datetime, text: str = "call Sam"):
    return store.add(text, fire_at, "UTC", NOW)


def test_store_add_list_cancel(tmp_path):
    store = make_store(tmp_path)
    later = seed(store, NOW + timedelta(hours=2), "later")
    sooner = seed(store, NOW + timedelta(hours=1), "sooner")
    assert [r.id for r in store.list_pending()] == [sooner.id, later.id]

    assert store.cancel(sooner.id) is True
    assert store.cancel(sooner.id) is False  # no longer pending
    assert [r.id for r in store.list_pending()] == [later.id]
    store.close()


def test_store_survives_a_restart(tmp_path):
    store = make_store(tmp_path)
    row = seed(store, NOW + timedelta(hours=1))
    store.close()

    reopened = make_store(tmp_path)
    (pending,) = reopened.list_pending()
    assert pending.id == row.id and pending.text == "call Sam"
    assert pending.fire_at == NOW + timedelta(hours=1)
    reopened.close()


def test_store_file_is_owner_only(tmp_path):
    store = make_store(tmp_path)
    seed(store, NOW + timedelta(hours=1))
    mode = stat.S_IMODE(os.stat(tmp_path / "data" / "reminders.db").st_mode)
    assert mode == 0o600
    store.close()


def test_claim_is_won_exactly_once_even_across_connections(tmp_path):
    first = make_store(tmp_path)
    second = make_store(tmp_path)
    row = seed(first, NOW - timedelta(minutes=1))  # already due

    assert first.claim(row.id, NOW, late=True) is True
    assert second.claim(row.id, NOW, late=True) is False
    assert second.get(row.id).status == "fired"
    first.close()
    second.close()


# ------------------------------------------------------------------ scheduler


def test_scheduler_fires_exactly_once(tmp_path):
    store = make_store(tmp_path)
    seed(store, NOW + timedelta(minutes=5))
    scheduler = ReminderScheduler(store, now=Clock())

    assert scheduler.fire_due(NOW + timedelta(minutes=4)) == []
    delivered = scheduler.fire_due(NOW + timedelta(minutes=5))
    assert [e.text for e in delivered] == ["call Sam"]
    assert scheduler.fire_due(NOW + timedelta(minutes=6)) == []
    assert len(store.list_inbox()) == 1
    store.close()


def test_scheduler_missed_fire_is_delivered_once_marked_late(tmp_path):
    store = make_store(tmp_path)
    # Came due at 12:00 while the process was down; scheduler starts 13:00.
    seed(store, NOW)
    scheduler = ReminderScheduler(store, now=lambda: NOW + timedelta(hours=1))
    scheduler.start()

    delivered = scheduler.fire_due(NOW + timedelta(hours=1))
    assert len(delivered) == 1
    assert delivered[0].late is True
    assert scheduler.fire_due(NOW + timedelta(hours=2)) == []
    store.close()


def test_scheduler_on_time_delivery_is_not_late(tmp_path):
    store = make_store(tmp_path)
    scheduler = ReminderScheduler(store, now=Clock())  # starts at NOW
    scheduler.start()
    seed(store, NOW + timedelta(minutes=5))

    delivered = scheduler.fire_due(NOW + timedelta(minutes=5, seconds=3))
    assert len(delivered) == 1
    assert delivered[0].late is False
    store.close()


async def test_scheduler_run_loop_delivers(tmp_path):
    store = make_store(tmp_path)
    seed(store, NOW - timedelta(seconds=1))
    seen: list[str] = []
    scheduler = ReminderScheduler(
        store, poll_interval=0.01, on_deliver=lambda e: seen.append(e.text), now=Clock()
    )
    scheduler.start_task()
    try:
        await asyncio.sleep(0.1)
    finally:
        await scheduler.stop()
    assert seen == ["call Sam"]
    store.close()


async def test_scheduler_run_loop_survives_a_failed_sweep(tmp_path, monkeypatch):
    store = make_store(tmp_path)
    seed(store, NOW - timedelta(seconds=1))
    seen: list[str] = []
    scheduler = ReminderScheduler(
        store, poll_interval=0.01, on_deliver=lambda e: seen.append(e.text), now=Clock()
    )
    real_fire_due = scheduler.fire_due
    sweeps = 0

    def flaky(now=None):
        nonlocal sweeps
        sweeps += 1
        if sweeps == 1:
            raise RuntimeError("store hiccup")
        return real_fire_due(now)

    monkeypatch.setattr(scheduler, "fire_due", flaky)
    scheduler.start_task()
    try:
        await asyncio.sleep(0.1)
    finally:
        await scheduler.stop()
    assert sweeps >= 2  # the failed first tick did not end the loop
    assert seen == ["call Sam"]
    store.close()


async def test_scheduler_run_loop_waits_between_failed_sweeps(tmp_path, monkeypatch):
    store = make_store(tmp_path)
    scheduler = ReminderScheduler(store, poll_interval=0.05, now=Clock())
    sweeps = 0

    def always_broken(now=None):
        nonlocal sweeps
        sweeps += 1
        raise RuntimeError("store is down")

    monkeypatch.setattr(scheduler, "fire_due", always_broken)
    scheduler.start_task()
    try:
        await asyncio.sleep(0.24)
    finally:
        await scheduler.stop()
    # A hot loop would sweep thousands of times in this window; the
    # guarded loop keeps the poll interval between failures (~5 ticks).
    assert 2 <= sweeps <= 10
    store.close()


def test_scheduler_one_bad_delivery_does_not_block_the_sweep(tmp_path, monkeypatch):
    store = make_store(tmp_path)
    bad = seed(store, NOW, "bad row")
    seed(store, NOW, "good row")
    real_deliver = store.deliver

    def flaky_deliver(reminder, delivered_at):
        if reminder.id == bad.id:
            raise RuntimeError("inbox insert failed")
        return real_deliver(reminder, delivered_at)

    monkeypatch.setattr(store, "deliver", flaky_deliver)
    scheduler = ReminderScheduler(store, now=Clock())

    delivered = scheduler.fire_due(NOW)
    assert [e.text for e in delivered] == ["good row"]
    # The bad row's claim was won before its delivery failed, so the
    # fire is on record: it is never retried (no duplicate later) and
    # it has no inbox entry. The failure is in the log, not silent.
    claimed = store.get(bad.id)
    assert claimed is not None and claimed.status == "fired"
    assert [e.text for e in store.list_inbox()] == ["good row"]
    assert scheduler.fire_due(NOW + timedelta(minutes=1)) == []
    store.close()


# ------------------------------------------------------- background watch


async def test_watch_task_logs_a_dead_background_task(caplog):
    async def boom():
        raise RuntimeError("loop exploded")

    task = watch_task("reminders", asyncio.create_task(boom()))
    await asyncio.sleep(0.05)
    assert task.done()
    errors = [r for r in caplog.records if r.levelname == "ERROR"]
    assert len(errors) == 1
    assert "reminders" in errors[0].message
    assert "RuntimeError" in errors[0].message


async def test_watch_task_is_quiet_when_a_task_ends_normally_or_is_cancelled(caplog):
    async def fine():
        return None

    async def forever():
        await asyncio.sleep(60)

    done = watch_task("offers", asyncio.create_task(fine()))
    await done
    stopped = watch_task("offers", asyncio.create_task(forever()))
    stopped.cancel()
    await asyncio.sleep(0.05)
    assert stopped.cancelled()
    assert not [r for r in caplog.records if r.levelname == "ERROR"]


# ------------------------------------------------------------------- commands


class Typed:
    async def __call__(self, prompt: str) -> str:
        return ""


def make_commands(tmp_path, clock: Clock | None = None):
    store = make_store(tmp_path)
    commands = ReminderCommands(store, tz=UTC, now=clock or Clock())
    return store, commands


async def test_commands_set_list_cancel(tmp_path):
    store, commands = make_commands(tmp_path)
    out = await commands.handle("/remind in 20 minutes call Sam", Typed())
    assert out is not None and "Reminder #1" in out[0] and "call Sam" in out[0]

    out = await commands.handle("/reminders", Typed())
    assert out is not None and "#1" in out[0] and "call Sam" in out[0]

    out = await commands.handle("/reminders cancel 1", Typed())
    assert out == ["Cancelled reminder #1."]
    assert store.list_pending() == []
    store.close()


async def test_commands_unparseable_remind_asks_for_a_clearer_time(tmp_path):
    store, commands = make_commands(tmp_path)
    out = await commands.handle("/remind sometime call Sam", Typed())
    assert out is not None and "couldn't work out" in out[0]
    assert store.list_pending() == []
    store.close()


async def test_commands_inbox_and_fallthrough(tmp_path):
    store, commands = make_commands(tmp_path)
    seed(store, NOW - timedelta(minutes=1))
    ReminderScheduler(store, now=Clock()).fire_due(NOW)

    out = await commands.handle("/inbox", Typed())
    assert out is not None and "call Sam" in out[0] and "(late" in out[0]

    # Not this handler's commands: return None so the chain can continue.
    assert await commands.handle("/memories", Typed()) is None
    assert await commands.handle("hello", Typed()) is None
    store.close()


# ------------------------------------------------------------- orchestrator


def make_service(tmp_path) -> tuple[ReminderStore, ReminderService]:
    store = make_store(tmp_path)
    return store, ReminderService(store, UTC)


async def test_respond_remind_me_sets_a_reminder_without_a_model_call(tmp_path):
    store, service = make_service(tmp_path)
    model = FakeModel(script=[])  # any model call raises
    orch, _ = await make_orchestrator(model, reminders=service)

    reply = await orch.respond("Remind me in 20 minutes to call Sam")

    assert "call Sam" in reply and "12:20 PM" in reply
    assert model.calls == []
    (pending,) = store.list_pending()
    assert pending.text == "call Sam"
    assert pending.fire_at == NOW + timedelta(minutes=20)
    store.close()


async def test_respond_remind_me_unparseable_asks_instead_of_guessing(tmp_path):
    store, service = make_service(tmp_path)
    model = FakeModel(script=[])
    orch, _ = await make_orchestrator(model, reminders=service)

    reply = await orch.respond("remind me sometime to do the thing")

    assert "couldn't work out when" in reply
    assert model.calls == []
    assert store.list_pending() == []
    store.close()


async def test_respond_other_turns_still_reach_the_model(tmp_path):
    store, service = make_service(tmp_path)
    model = FakeModel(script=[resp(text("Hello."))])
    orch, _ = await make_orchestrator(model, reminders=service)

    assert await orch.respond("hello there") == "Hello."
    assert store.list_pending() == []
    store.close()


async def test_respond_without_reminders_configured_uses_the_model(tmp_path):
    model = FakeModel(script=[resp(text("Sure."))])
    orch, _ = await make_orchestrator(model)  # no reminders service

    assert await orch.respond("remind me in 20 minutes to call Sam") == "Sure."


# --------------------------------------------------------------------- config


def test_config_reminders_defaults_and_overrides():
    base = {"SUTRA_TOKEN": "t", "ANTHROPIC_API_KEY": "k"}
    config = load_config({**base}, dotenv_path=None)
    assert config.reminders_enabled is True
    assert config.reminders_tz == "America/Denver"

    config = load_config(
        {**base, "SUTRA_REMINDERS": "off", "SUTRA_REMINDERS_TZ": "UTC"},
        dotenv_path=None,
    )
    assert config.reminders_enabled is False
    assert config.reminders_tz == "UTC"

    with pytest.raises(ConfigError):
        load_config({**base, "SUTRA_REMINDERS_TZ": "Not/AZone"}, dotenv_path=None)


# ------------------------------------------------- natural phrasings (trailing time etc.)


def test_time_may_follow_the_reminder_text():
    got = parse("to call Sam at 5pm")
    assert got is not None and got.text == "call Sam"
    assert got.fire_at.hour == 17
    got = parse("to buy milk in twenty minutes")
    assert got is not None and got.text == "buy milk"
    assert got.fire_at == NOW + timedelta(minutes=20)


def test_weekday_and_date_default_to_nine_am_and_are_explicit_when_given():
    got = parse("on Friday to pay rent")
    assert got is not None and got.text == "pay rent"
    assert (got.fire_at.hour, got.fire_at.minute, got.fire_at.weekday()) == (9, 0, 4)
    got = parse("to email Ann at 2pm on Friday")
    assert got is not None and got.fire_at.hour == 14 and got.fire_at.weekday() == 4
    got = parse("on December 20th to renew passport")
    assert got is not None and (got.fire_at.month, got.fire_at.day) == (12, 20)


def test_next_weekday_means_next_week():
    # NOW is Monday 12 October 2026.
    assert parse("on Friday to x").fire_at.day == 16
    assert parse("next Friday to x").fire_at.day == 23
    assert parse("next Tuesday to x").fire_at.day == 20  # not tomorrow


def test_bare_hour_needs_a_part_of_day():
    got = parse("to take my pills at 8 tonight")
    assert got is not None and got.fire_at.hour == 20
    assert parse("to call mom at 3") is None
    assert parse("to run tomorrow morning") is None  # no exact time: ask


def test_two_times_or_no_text_ask_instead_of_guessing():
    assert parse("to call at 3pm and at 4pm") is None
    assert parse("to call in 5 minutes at 4pm") is None
    assert parse("to call Sam") is None


def test_leading_phrases_and_questions():
    assert reminder_request("Can you remind me in an hour to stretch?") == "in an hour to stretch?"
    assert reminder_request("set a reminder for 5pm to call Sam") == "for 5pm to call Sam"
    assert parse("for 5pm to call Sam").text == "call Sam"
    assert reminder_request("remind me what I said yesterday") is None
    assert reminder_request("remind me of my goals") is None


# ------------------------------------------ real speech: fillers, spoken hours, "9 a.m."

DEN_NOW = datetime(2026, 11, 3, 14, 0, tzinfo=DENVER)  # a Tuesday afternoon


@pytest.mark.parametrize(
    "said",
    [
        "So lets remind me in 2 minutes to stretch",
        "Okay, so can you remind me in 2 minutes to stretch?",
        "Hey Sutra, could you please remind me in 2 minutes to stretch",
        "I want you to remind me in 2 minutes to stretch",
        "um, remind me in 2 minutes to stretch",
    ],
)
def test_ordinary_filler_before_remind_me_is_fine(said):
    request = reminder_request(said)
    assert request is not None and "in 2 minutes to stretch" in request
    got = parse_request(request, DEN_NOW, DENVER)
    assert got is not None and got.text == "stretch" and got.fire_at == DEN_NOW + timedelta(minutes=2)


@pytest.mark.parametrize(
    "said",
    [
        "don't remind me about that",
        "did you remind me yet",
        "I told her to remind me later",
        "why would you remind me of that",
        "she might remind me in 2 minutes to stretch",
        "one two three four five six seven eight nine remind me in 2 minutes to stretch",
    ],
)
def test_anything_else_before_remind_me_is_not_a_request(said):
    assert reminder_request(said) is None


def test_spoken_hours_and_spaced_am_pm_and_dayparts_parse():
    for said, hour, text_ in [
        ("tomorrow at nine in the morning to call Sam", 9, "call Sam"),
        ("tomorrow at 9 A.M. to call Sam", 9, "call Sam"),
        ("tomorrow at 9 am to call Sam", 9, "call Sam"),
        ("at 5 PM to stretch", 17, "stretch"),
        ("at five o'clock this evening to stretch", 17, "stretch"),
        ("at 9 at night to lock up", 21, "lock up"),
    ]:
        got = parse_request(said, DEN_NOW, DENVER)
        assert got is not None, said
        assert (got.fire_at.hour, got.text) == (hour, text_), said


def test_bare_hours_are_still_not_guessed_by_the_strict_parser():
    assert parse_request("tomorrow at 9 to call Sam", DEN_NOW, DENVER) is None
    assert parse_request("at 5 to do stuff", DEN_NOW, DENVER) is None


def test_bare_hour_with_no_day_picks_the_next_one_coming_in_waking_hours():
    from sutra_orchestrator.reminders.parser import resolve_bare_hour

    pick = lambda r: resolve_bare_hour(r, DEN_NOW, DENVER).chosen.fire_at.strftime("%a %H:%M")
    assert pick("at 8 to take my pills") == "Tue 20:00"  # 8 PM tonight, not 8 AM tomorrow
    assert pick("at one o'clock to eat") == "Wed 13:00"  # never 1 in the morning
    assert pick("at 3 to call Sam") == "Tue 15:00"
    # A day named means two real readings: the caller must ask.
    both = resolve_bare_hour("tomorrow at nine to call Sam", DEN_NOW, DENVER)
    assert both.chosen is None and both.am.fire_at.hour == 9 and both.pm.fire_at.hour == 21
    assert resolve_bare_hour("sometime to do the thing", DEN_NOW, DENVER) is None


async def test_the_dentist_example_asks_morning_or_evening_then_saves_the_answer(tmp_path):
    store = make_store(tmp_path)
    service = ReminderService(store, DENVER)
    model = FakeModel(script=[])  # no model call anywhere in this flow
    clock = Clock(DEN_NOW)
    orch, _ = await make_orchestrator(model, reminders=service, clock=clock)

    ask = await orch.respond("Okay, so can you remind me tomorrow at nine to call the dentist?")
    assert "Do you mean tomorrow at 9:00 AM or tomorrow at 9:00 PM" in ask and "morning or evening" in ask
    assert store.list_pending() == []  # nothing set until they answer

    done = await orch.respond("the morning")
    assert "call the dentist" in done and "tomorrow at 9:00 AM" in done
    [row] = store.list_pending()
    assert row.text == "call the dentist" and row.fire_at.astimezone(DENVER).hour == 9
    assert model.calls == []
    store.close()


async def test_an_answer_that_is_not_an_answer_closes_the_question_without_a_reminder(tmp_path):
    store = make_store(tmp_path)
    service = ReminderService(store, DENVER)
    model = FakeModel(script=[resp(text("It is two in the afternoon."))])
    orch, _ = await make_orchestrator(model, reminders=service, clock=Clock(DEN_NOW))
    await orch.respond("remind me tomorrow at nine to call the dentist")
    reply = await orch.respond("what time is it")  # carries on as an ordinary turn
    assert reply == "It is two in the afternoon."
    assert store.list_pending() == []
    # The question is gone: a later "morning" is not read as an answer.
    assert service.try_handle("morning", DEN_NOW) is None
    store.close()


async def test_a_stale_question_is_not_answered_by_a_much_later_word(tmp_path):
    store = make_store(tmp_path)
    service = ReminderService(store, DENVER)
    service.try_handle("remind me tomorrow at nine to call the dentist", DEN_NOW)
    assert service.try_handle("morning", DEN_NOW + timedelta(minutes=10)) is None
    assert store.list_pending() == []
    store.close()


async def test_a_bare_hour_today_is_set_to_the_next_one_and_says_so(tmp_path):
    store = make_store(tmp_path)
    service = ReminderService(store, DENVER)
    reply = service.try_handle("remind me at 8 to take my pills", DEN_NOW)
    assert "take my pills" in reply and "today at 8:00 PM" in reply  # the exact time is spoken back
    store.close()


def test_the_model_is_told_not_to_send_reminders_to_the_money_calendar():
    from sutra_orchestrator.prompts import load_prompt

    prompt = load_prompt("system.md")
    assert "Never say you cannot set reminders" in prompt and "money calendar" in prompt
    assert "Say what you heard and ask them to repeat" in prompt  # the "Zoram" rule
