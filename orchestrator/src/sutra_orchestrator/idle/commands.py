"""REPL commands for idle research."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import time

from .service import IdleResearcher

HELP = [
    "Idle research commands:",
    "  /idle                 status, today's use and recent runs",
    "  /idle on | off        turn idle research on or off",
    "  /idle now             try one run now (ignores quiet time, not budgets or blocks)",
    "  /idle show <id>       the summary and full findings of one run",
    "  /idle forget          delete the run record",
]


class IdleCommands:
    def __init__(self, researcher: IdleResearcher) -> None:
        self._r = researcher
        self._store = researcher.store

    async def handle(self, line: str, read: Callable[[str], Awaitable[str]]) -> list[str] | None:
        line = line.strip()
        if not line.startswith("/"):
            return None
        command, _, rest = line[1:].partition(" ")
        if command.lower() != "idle":
            return None
        sub, _, arg = rest.strip().partition(" ")
        sub, arg = sub.lower(), arg.strip()
        if sub == "":
            return self._status()
        if sub in ("on", "off"):
            self._r.set_enabled(sub == "on")
            return [f"Idle research is {sub}."]
        if sub == "now":
            if not self._r.enabled:
                return ["Idle research is off. Turn it on with /idle on."]
            try:
                return [await self._r.maybe_run(force=True)]
            except Exception as exc:
                return [f"That failed ({type(exc).__name__}); nothing was changed."]
        if sub == "show":
            run = self._store.get(int(arg.lstrip("#"))) if arg.lstrip("#").isdigit() else None
            if run is None:
                return ["Usage: /idle show <id>"]
            return [
                f"#{run.id} {run.topic} [{run.outcome}] {run.created_at:%Y-%m-%d %H:%M}",
                f"  asked: {run.brief}",
                f"  summary: {run.summary or '(none)'}",
                f"  findings: {run.findings or '(none)'}",
            ]
        if sub == "forget":
            return [f"Deleted {self._store.forget_all()} run(s)."]
        return HELP

    def _status(self) -> list[str]:
        now = self._r._now()
        why = self._r.blocker()
        local = now.astimezone(self._r._tz)
        midnight = __import__("datetime").datetime.combine(local.date(), time.min, tzinfo=self._r._tz)
        lines = [
            f"Idle research is {'on' if self._r.enabled else 'off'}."
            + (f" Not running now: {why}." if why else " It may run when you are away."),
            f"  runs today: {self._store.ran_since(midnight)}",
        ]
        for run in self._store.recent(8):
            lines.append(f"  #{run.id} {run.created_at:%m-%d %H:%M} [{run.outcome}] {run.topic}")
        if len(lines) == 2:
            lines.append("  Nothing researched yet.")
        return lines
