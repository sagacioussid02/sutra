"""REPL commands for the feeds."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from .service import FeedService

HELP = [
    "Feed commands:",
    "  /feeds              what is on, your area, and when each was last checked",
    "  /feeds news on|off  headline roundups on topics you care about (off by default)",
    "  /feeds check        check the feeds now",
]


class FeedCommands:
    def __init__(self, service: FeedService) -> None:
        self._service = service

    async def handle(self, line: str, read: Callable[[str], Awaitable[str]]) -> list[str] | None:
        line = line.strip()
        if not line.startswith("/"):
            return None
        command, _, rest = line[1:].partition(" ")
        if command.lower() != "feeds":
            return None
        parts = rest.split()
        s = self._service
        if not parts:
            def when(feed: str) -> str:
                t = s.last(feed)
                return f"last checked {t.astimezone(s._tz):%b %d %H:%M}" if t else "not checked yet"

            return [
                f"Weather: {'on for ' + s.area + ' (only the place name is sent)' if s.area else 'off (set SUTRA_HOME_AREA to turn it on)'}"
                + (f"; {when('weather')}" if s.area else ""),
                f"News: {'on' if s.news_enabled else 'off'} ({when('news')})" + ("; only a topic word is sent" if s.news_enabled else ""),
            ]
        if parts[0] == "news" and len(parts) == 2 and parts[1] in ("on", "off"):
            s.set_news(parts[1] == "on")
            return [f"News is {parts[1]}."]
        if parts[0] == "check":
            await s.poll()
            return ["Checked."]
        return HELP
