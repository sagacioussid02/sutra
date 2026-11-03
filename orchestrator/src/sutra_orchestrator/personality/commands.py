"""REPL commands for the humor profile."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from .service import PersonalityService
from .store import LEVEL_MAX, STYLES, VARIETY_HIGH, VARIETY_LOW

HELP = [
    "Humor commands:",
    "  /humor                    show the level, variety and how each style has landed",
    "  /humor level <0-10>       how often to joke (0 is never)",
    "  /humor variety <0.2-2>    low sticks to what works, high tries other styles",
    "  /humor style <name> <0-1> set one style's score by hand",
    "  /humor off | on           stop or resume jokes",
    "  /humor reset              back to the defaults",
]


class HumorCommands:
    def __init__(self, service: PersonalityService) -> None:
        self._service = service
        self._store = service.store

    async def handle(self, line: str, read: Callable[[str], Awaitable[str]]) -> list[str] | None:
        line = line.strip()
        if not line.startswith("/"):
            return None
        command, _, rest = line[1:].partition(" ")
        if command.lower() != "humor":
            return None
        parts = rest.split()
        sub = parts[0].lower() if parts else ""
        if sub == "":
            return self._show()
        try:
            if sub == "level" and len(parts) == 2:
                return [f"Level is {self._store.set_level(int(parts[1]))} of {LEVEL_MAX}."]
            if sub == "variety" and len(parts) == 2:
                return [f"Variety is {self._store.set_variety(float(parts[1])):.2f} (from {VARIETY_LOW} to {VARIETY_HIGH})."]
            if sub == "style" and len(parts) == 3 and parts[1] in STYLES:
                self._store.set_score(parts[1], float(parts[2]))
                return [f"{parts[1]} is now {self._store.scores()[parts[1]]:.2f}."]
        except ValueError:
            return ["That needs a number."]
        if sub in ("off", "on"):
            self._store.set_enabled(sub == "on")
            if sub == "on" and self._store.level == 0:
                self._store.set_level(self._store.last_level)
            return [f"Humor is {sub}."]
        if sub == "reset":
            self._store.reset()
            return ["Humor is back to the defaults."]
        return HELP

    def _show(self) -> list[str]:
        s = self._store
        lines = [
            f"Humor is {'on' if s.enabled else 'off'}: level {s.level} of {LEVEL_MAX} "
            f"(about one eligible turn in {max(1, round(24 / s.level)) if s.level else 'never'}), variety {s.variety:.2f}.",
        ]
        for r in s.style_rows():
            lines.append(
                f"  {r['style']:<9} score {r['score']:.2f}  tried {r['tries']}: "
                f"{r['laughed']} laughed, {r['smiled']} smiled, {r['neutral']} neutral, "
                f"{r['groaned']} groaned, {r['annoyed']} annoyed"
            )
        return lines
