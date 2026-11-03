"""REPL commands for the mode. These need a keyboard, which is exactly why they may raise it."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from .service import Mode, SafetyService

HELP = [
    "Mode commands:",
    "  /mode                  show the mode",
    "  /mode full             everything",
    "  /mode limited          only answer and look things up; nothing changed, nothing unprompted",
    "  /mode off              switched off",
]
DESCRIBE = {
    Mode.FULL: "full: everything.",
    Mode.LIMITED: "limited: answers and looks things up only. No changes, no spending, nothing unprompted.",
    Mode.OFF: "off: not answering. Reminders still fire quietly.",
}


class ModeCommands:
    def __init__(self, safety: SafetyService) -> None:
        self._safety = safety

    async def handle(self, line: str, read: Callable[[str], Awaitable[str]]) -> list[str] | None:
        line = line.strip()
        if not line.startswith("/"):
            return None
        command, _, rest = line[1:].partition(" ")
        if command.lower() != "mode":
            return None
        arg = rest.strip().lower()
        if not arg:
            return [f"Mode is {DESCRIBE[self._safety.mode]}"]
        names = {"full": Mode.FULL, "limited": Mode.LIMITED, "off": Mode.OFF}
        if arg in names:
            self._safety.restore(names[arg])
            return [f"Mode is now {DESCRIBE[names[arg]]}"]
        return HELP
