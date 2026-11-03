"""REPL commands for people and plans."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import date

from .service import LifeService

HELP = [
    "Life commands:",
    "  /life                         people I know about and what you have coming up",
    "  /life add plan <date> <text>  add something coming up (date as YYYY-MM-DD, or - for none)",
    "  /life forget person <id>      forget one person",
    "  /life forget plan <id>        forget one plan",
    "  /life forget all              forget everyone and everything",
]


class LifeCommands:
    def __init__(self, service: LifeService) -> None:
        self._service = service
        self._store = service.store

    async def handle(self, line: str, read: Callable[[str], Awaitable[str]]) -> list[str] | None:
        line = line.strip()
        if not line.startswith("/"):
            return None
        command, _, rest = line[1:].partition(" ")
        if command.lower() != "life":
            return None
        parts = rest.split(None, 3)
        sub = parts[0].lower() if parts else ""
        if sub == "":
            out = [f"#{p.id} {p.name}" + (f" ({p.relation})" if p.relation else "") + f", mentioned {p.mentions}x"
                   for p in self._store.people()]
            out += [f"plan #{q.id} [{q.status}] {q.text}" + (f" on {q.when_date}" if q.when_date else "")
                    for q in self._store.plans(("upcoming", "asked"))]
            return out or ["Nothing yet. I learn about the people and plans in your life as you mention them."]
        if sub == "add" and len(parts) == 4 and parts[1] == "plan":
            try:
                when = None if parts[2] == "-" else date.fromisoformat(parts[2])
            except ValueError:
                return ["Use a date like 2026-11-20, or - for none."]
            made = self._store.add_plan(parts[3][:80], "", when, self._service._now())
            return ["Added."] if made else ["I already have that, or the list is full."]
        if sub == "forget" and len(parts) >= 2:
            if parts[1].lower() == "all":
                p, q = self._store.forget_all()
                return [f"Forgot {p} people and {q} plans."]
            if len(parts) == 3 and parts[2].lstrip("#").isdigit():
                ident = int(parts[2].lstrip("#"))
                if parts[1] == "person":
                    return ["Forgotten."] if self._store.forget_person(ident) else ["No such person."]
                if parts[1] == "plan":
                    return ["Forgotten."] if self._store.forget_plan(ident) else ["No such plan."]
        return HELP
