"""The /state command: the snapshot exactly as consumers see it, with ages."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from .provider import WorldState
from .snapshot import age_text
from .sources import PRESENCE_VALUES, Presence

HELP = [
    "State commands:",
    "  /state                         what I can observe right now, with ages",
    f"  /state presence <{'|'.join(PRESENCE_VALUES)}>   tell me roughly where you are",
    "  /state presence clear          forget it",
    "  /state off | on                stop or resume using it in replies",
]


class StateCommands:
    def __init__(self, world: WorldState, presence: Presence) -> None:
        self._world = world
        self._presence = presence

    async def handle(self, line: str, read: Callable[[str], Awaitable[str]]) -> list[str] | None:
        line = line.strip()
        if not line.startswith("/"):
            return None
        command, _, rest = line[1:].partition(" ")
        if command.lower() != "state":
            return None
        sub, _, arg = rest.strip().partition(" ")
        sub, arg = sub.lower(), arg.strip().lower()
        if sub in ("off", "on"):
            self._world.enabled = sub == "on"
            return [f"World state is {sub}."]
        if sub == "presence":
            if arg == "clear":
                self._presence.clear()
                return ["Presence cleared."]
            if self._presence.set(arg):
                return [f"Noted: {arg}."]
            return [f"Usage: /state presence <{'|'.join(PRESENCE_VALUES)}|clear>"]
        if sub:
            return HELP
        return await self._overview()

    async def _overview(self) -> list[str]:
        snap = await self._world.snapshot()
        now = self._world._now()
        lines = [f"World state is {'on' if self._world.enabled else 'off (replies do not use it)'}."]
        shown = snap.render(now, 10_000)
        lines += shown.splitlines() if shown else ["Nothing observed."]
        for name, why in sorted(snap.absent.items()):
            lines.append(f"  not observed: {name} ({why})")
        lines.append(f"  assembled {age_text(snap.assembled_at, now)}; sources: "
                     + ", ".join(f"{f.name}={f.source}" for f in snap.fields.values()))
        return lines
