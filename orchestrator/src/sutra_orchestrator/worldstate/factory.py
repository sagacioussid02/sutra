"""Build the world-state provider from the services that already exist."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from ..config import Config
from .provider import FieldSpec, WorldState
from .sources import (
    Presence,
    ToolSeen,
    calendar_reader,
    commitments_reader,
    events_reader,
)


def build_worldstate(
    config: Config,
    *,
    call_tool: Callable,
    permitted: Callable[[str], bool],
    pending: Callable[[], object | None],
    offers=None,
    reminders=None,
    graph=None,
    events=None,
    now: Callable[[], datetime] | None = None,
) -> tuple[WorldState, Presence, ToolSeen] | None:
    if not config.worldstate_enabled:
        return None
    clock = now or (lambda: datetime.now(timezone.utc))
    tz = ZoneInfo(config.reminders_tz)
    presence, seen = Presence(clock), ToolSeen(clock)
    minutes = lambda n: timedelta(minutes=n)  # noqa: E731
    specs = [
        FieldSpec("presence", "Where they are", "user-set hint", presence.read, None),
        FieldSpec(
            "calendar", "Coming up", "finanxe calendar",
            calendar_reader(call_tool, permitted, tz, clock), minutes(config.worldstate_calendar_ttl), cached=True,
        ),
        FieldSpec("finance", "Finance", "finanxe snapshot pointer", seen.finance_reader(), minutes(config.worldstate_finance_ttl)),
        FieldSpec(
            "commitments", "Open", "reminders, offers, confirmations, graph",
            commitments_reader(tz, clock, pending=pending, offers=offers, reminders=reminders, graph=graph),
            minutes(1),
        ),
    ]
    if events is not None:
        specs.append(FieldSpec("events", "Just in", "inbound event log", events_reader(events, clock), None))
    world = WorldState(specs, timeout=config.worldstate_timeout, budget=config.worldstate_chars, now=clock)
    return world, presence, seen
