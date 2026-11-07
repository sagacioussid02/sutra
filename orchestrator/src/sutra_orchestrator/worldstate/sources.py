"""Readers for each field. Each asks the store that owns the truth; none writes anything."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from .provider import Reading

PRESENCE_VALUES = ("home", "out", "busy", "do-not-disturb")
CALENDAR_TOOL = "finanxe_get_calendar"
FINANCE_TOOL = "finanxe_get_snapshot"
_TAGS = re.compile(r"[<>]")


def clean(text: object, limit: int = 80) -> str:
    """Outside text, made safe to quote: one line, no angle brackets, bounded."""
    return _TAGS.sub("", " ".join(str(text).split()))[:limit]


class Presence:
    """A coarse, user-set hint. In memory only: after a restart it is simply not known."""

    def __init__(self, now: Callable[[], datetime]) -> None:
        self._now = now
        self._value: str | None = None
        self._set_at: datetime | None = None

    def set(self, value: str) -> bool:
        if value not in PRESENCE_VALUES:
            return False
        self._value, self._set_at = value, self._now()
        return True

    def clear(self) -> None:
        self._value = self._set_at = None

    @property
    def value(self) -> str | None:
        return self._value

    async def read(self) -> Reading | None:
        return Reading(self._value, self._set_at) if self._value and self._set_at else None


class ToolSeen:
    """When a read-only tool last returned successfully this session (a pointer, never the figures)."""

    def __init__(self, now: Callable[[], datetime]) -> None:
        self._now = now
        self._seen: dict[str, datetime] = {}

    def note(self, name: str) -> None:
        if name == FINANCE_TOOL:
            self._seen[name] = self._now()

    def finance_reader(self):
        async def read() -> Reading | None:
            at = self._seen.get(FINANCE_TOOL)
            if at is None:
                return None
            return Reading(f"last looked at through {FINANCE_TOOL}; no figures are kept here, ask for them fresh", at)

        return read


def calendar_reader(
    call: Callable[[str, dict], object],
    permitted: Callable[[str], bool],
    tz: ZoneInfo,
    now: Callable[[], datetime],
    days: int = 3,
):
    """Upcoming items from the existing calendar tool. Honours the current mode and authentication."""

    async def read() -> str | None:
        if not permitted(CALENDAR_TOOL):
            return None
        result = await call(CALENDAR_TOOL, {})  # type: ignore[misc]
        if getattr(result, "kind", "") != "ok":
            raise RuntimeError("calendar unavailable")
        events = json.loads(result.text).get("events") or []
        today = now().astimezone(tz).date()
        horizon = today + timedelta(days=days)
        upcoming: list[tuple[date, str]] = []
        for e in events:
            try:
                when = date.fromisoformat(str(e.get("date", ""))[:10])
            except ValueError:
                continue
            if today <= when <= horizon and e.get("title"):
                upcoming.append((when, clean(e["title"], 60)))
        if not upcoming:
            return f"nothing scheduled in the next {days} days"
        upcoming.sort()
        parts = [("today" if d == today else f"{d:%a %d %b}") + f": {t}" for d, t in upcoming[:5]]
        return "; ".join(parts)

    return read


def commitments_reader(
    tz: ZoneInfo,
    now: Callable[[], datetime],
    *,
    pending: Callable[[], object | None],
    offers,
    reminders,
    graph,
):
    """Open commitments, read from their owners at assembly time. Reports; never resolves or expires."""

    async def read() -> str:
        parts: list[str] = []
        action = pending()
        if action is not None:
            parts.append(f"1 action waiting for a yes or no ({clean(getattr(action, 'description', 'an action'), 80)})")
        if offers is not None:
            n = len(offers.store.open_offers())
            if n:
                parts.append(f"{n} offer{'s' if n != 1 else ''} not yet answered")
        if reminders is not None:
            due = sorted(reminders.list_pending(), key=lambda r: r.fire_at)[:3]
            if due:
                parts.append(
                    "reminders: "
                    + "; ".join(f"{clean(r.text, 40)} at {r.fire_at.astimezone(tz):%a %H:%M}" for r in due)
                )
        if graph is not None:
            nodes = [n for n in graph.store.list() if n.open]
            if nodes:
                parts.append("left open in conversation: " + "; ".join(clean(n.topic, 40) for n in nodes[:3]))
        return ", ".join(parts) if parts else "nothing open"

    return read


def events_reader(events, now: Callable[[], datetime]):
    """Unexpired events from the inbound log, quoted only inside an untrusted label."""

    async def read() -> Reading | None:
        from ..events import untrusted_block  # local: events imports offers

        t = now()
        fresh = [e for e in events.store.recent(20) if e.expires_at > t][:3]
        if not fresh:
            return None
        lines = []
        for e in fresh:
            minutes = max(0, int((t - e.received_at).total_seconds() // 60))
            lines.append(f"{minutes} min ago {untrusted_block(e)}")
        return Reading(" | ".join(lines), max(e.received_at for e in fresh))

    return read
