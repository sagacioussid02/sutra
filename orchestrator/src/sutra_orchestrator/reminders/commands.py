"""REPL commands for reminders, following the memory commands' pattern.

Lines starting with ``/`` are handled here and never reach the model. This
handler returns None for any command it does not own, so it can sit in a
chain with the memory commands.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from .parser import parse_request
from .service import spoken_when
from .store import ReminderRow, ReminderStore

HELP = [
    "Reminder commands:",
    "  /remind <when> <what>   set a reminder, e.g. /remind in 20 minutes call Sam",
    "                          (in N minutes/hours, at 5pm, today at 5pm, tomorrow at 9am)",
    "  /reminders              list pending reminders",
    "  /reminders cancel <id>  cancel a pending reminder",
    "  /inbox                  reminders that have fired",
]

_USAGE = "Usage: /remind in 20 minutes call Sam   (also: at 5pm, tomorrow at 9am)"


class ReminderCommands:
    def __init__(
        self,
        store: ReminderStore,
        *,
        tz: ZoneInfo,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._store = store
        self._tz = tz
        self._now = now or (lambda: datetime.now(timezone.utc))

    async def handle(
        self, line: str, read: Callable[[str], Awaitable[str]]
    ) -> list[str] | None:
        """Run a command. Returns the lines to show, or None if ``line``
        is not one of this handler's commands."""
        line = line.strip()
        if not line.startswith("/"):
            return None
        command, _, rest = line[1:].partition(" ")
        handler = {
            "remind": self._remind,
            "reminders": self._reminders,
            "inbox": self._inbox,
        }.get(command.lower())
        if handler is None:
            return None
        return await handler(rest.strip())

    # -- helpers ---------------------------------------------------------------

    def _when(self, row: ReminderRow) -> str:
        return spoken_when(row.fire_at, self._now(), self._tz)

    # -- commands -----------------------------------------------------------------

    async def _remind(self, rest: str) -> list[str]:
        now = self._now()
        parsed = parse_request(rest, now, self._tz)
        if parsed is None or not parsed.text:
            return ["I couldn't work out when you mean.", _USAGE]
        row = self._store.add(parsed.text, parsed.fire_at, str(self._tz), now)
        return [f"Reminder #{row.id} set for {self._when(row)}: {row.text}"]

    async def _reminders(self, rest: str) -> list[str]:
        sub, _, arg = rest.partition(" ")
        if sub == "cancel":
            reminder_id = arg.strip().lstrip("#")
            if not reminder_id.isdigit():
                return ["Usage: /reminders cancel <id>"]
            if self._store.cancel(int(reminder_id)):
                return [f"Cancelled reminder #{reminder_id}."]
            return [f"There is no pending reminder #{reminder_id}."]
        if rest:
            return ["Usage: /reminders   or   /reminders cancel <id>"]
        rows = self._store.list_pending()
        if not rows:
            return ["No reminders pending."]
        return [f"#{r.id} {self._when(r)}: {r.text}" for r in rows]

    async def _inbox(self, rest: str) -> list[str]:
        rows = self._store.list_inbox()
        if not rows:
            return ["Nothing has fired yet."]
        lines = []
        for entry in rows:
            late = " (late — it came due while I was off)" if entry.late else ""
            seen = "" if entry.seen else " [new]"
            lines.append(f"#{entry.id} {entry.text}{late}{seen}")
        return lines
