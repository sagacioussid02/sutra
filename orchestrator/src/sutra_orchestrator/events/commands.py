"""REPL commands for the event log: what arrived, from whom, and whether it was delivered."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime

from .kinds import Event
from .service import EventsService

HELP = [
    "Event commands:",
    "  /events            recent events, per-source counts, log size",
    "  /events off | on   stop or resume taking in and delivering events",
]


def age_text(then: datetime, now: datetime) -> str:
    minutes = int((now - then).total_seconds() // 60)
    if minutes < 1:
        return "just now"
    if minutes < 60:
        return f"{minutes} min ago"
    return f"{minutes // 60} h ago" if minutes < 1440 else f"{minutes // 1440} d ago"


class EventsCommands:
    def __init__(self, service: EventsService) -> None:
        self._service = service

    async def handle(self, line: str, read: Callable[[str], Awaitable[str]]) -> list[str] | None:
        line = line.strip()
        if not line.startswith("/"):
            return None
        command, _, rest = line[1:].partition(" ")
        if command.lower() != "events":
            return None
        sub = rest.strip().lower()
        if sub in ("off", "on"):
            self._service.enabled = sub == "on"
            return [f"Events are {sub}."]
        if sub:
            return HELP
        return self._overview()

    def _delivery(self, event: Event, cursors: dict[str, int], consumers: list[str]) -> str:
        if not consumers:
            return "no consumers"
        return ", ".join(f"{c}: {'delivered' if cursors.get(c, 0) >= event.seq else 'waiting'}" for c in consumers)

    def _overview(self) -> list[str]:
        s, store = self._service, self._service.store
        now = s._now()
        lines = [f"Events are {'on' if s.enabled else 'off'}. {store.count()} in the log."]
        for source, n in store.per_source():
            lines.append(f"  {source}: {n}")
        cursors, consumers = store.cursors(), sorted(s._consumers)
        recent = store.recent(10)
        if not recent:
            lines.append("  No events yet.")
        for e in recent:
            expired = " (expired)" if e.expires_at <= now else ""
            lines.append(
                f"  {e.source}/{e.kind} {age_text(e.received_at, now)}{expired}: "
                f"{e.payload.get('summary', '')[:60]} [{self._delivery(e, cursors, consumers)}]"
            )
        for row in store.skipped()[:5]:
            lines.append(f"  skipped for {row['consumer']} after repeated failures: {row['error']}")
        return lines
