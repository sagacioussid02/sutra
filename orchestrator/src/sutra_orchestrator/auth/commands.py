"""REPL commands for the authentication flipper. These need a keyboard, which is why they may turn it off."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from .service import AuthService

HELP = [
    "Authentication commands:",
    "  /auth            is it on, how much there is to ask about, any cooldown or grant",
    "  /auth on | off   the feature flipper (off needs the keyboard, which is why it is a command)",
    "  /auth forget     delete every stored fact",
]


class AuthCommands:
    def __init__(self, service: AuthService) -> None:
        self._service = service

    async def handle(self, line: str, read: Callable[[str], Awaitable[str]]) -> list[str] | None:
        line = line.strip()
        if not line.startswith("/"):
            return None
        command, _, rest = line[1:].partition(" ")
        if command.lower() != "auth":
            return None
        arg = rest.strip().lower()
        s = self._service
        if arg in ("on", "off"):
            s.set_enabled(arg == "on")
            return [f"Authentication is {arg}."]
        if arg == "forget":
            return [f"Deleted {s.store.forget_all()} fact(s)."]
        if arg == "":
            st = s.status()
            lines = [f"Authentication is {'on' if st['enabled'] else 'off'}."]
            if st["enabled"]:
                lines.append(
                    f"  {st['facts']} usable fact(s) from {st['days']} day(s): "
                    f"{'can' if st['ready_mode'] else 'cannot yet'} check a return to full mode, "
                    f"{'can' if st['ready_action'] else 'cannot yet'} grant protected actions."
                )
                if st["locked_until"]:
                    lines.append(f"  Cooling down until {st['locked_until'].astimezone(s._tz):%H:%M}.")
                if st["grant"]:
                    lines.append("  A grant for protected actions is active.")
            return lines
        return HELP
