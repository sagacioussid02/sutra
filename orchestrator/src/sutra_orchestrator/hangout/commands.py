"""REPL commands for the group chat bridge."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from .service import HangoutService


class HangoutCommands:
    def __init__(self, service: HangoutService, url: str) -> None:
        self._service = service
        self._url = url

    async def handle(self, line: str, read: Callable[[str], Awaitable[str]]) -> list[str] | None:
        line = line.strip()
        if not line.startswith("/"):
            return None
        command, _, rest = line[1:].partition(" ")
        if command.lower() != "hangout":
            return None
        sub = rest.strip().lower()
        if sub == "reset":
            return ["The group's world was reset."] if await self._service.client.reset() else ["I couldn't reach the group app."]
        up = await self._service.client.ping()
        return [
            f"Group app at {self._url}: {'answering' if up else 'not answering'}.",
            "Say \"let's catch up with the group\" to step in; \"leave the group\" to come back. /hangout reset starts its world afresh.",
        ]
