"""REPL commands for the interest profile."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime

from .service import InterestService
from .store import InterestRow

HELP = [
    "Interest commands:",
    "  /interests                list what I know you're into",
    "  /interests why <id>       the things you said that led to it",
    "  /interests history <id>   how it changed over time",
    "  /interests approve <id>   keep a suggestion (or accept a change)",
    "  /interests reject <id>    decline a suggestion",
    "  /interests mute <id>      stop bringing it up",
    "  /interests add <topic>    tell me something you're into",
    "  /interests forget <id>    delete it and what it was based on",
    "  /interests forget all     delete everything",
    "  /interests reflect        look through recent conversations now",
]


def _describe(r: InterestRow) -> str:
    extra = ""
    if r.status == "proposed" and r.revises_id is not None:
        extra = f" (change from: {r.change_before})"
    elif r.status == "proposed":
        extra = " (suggested, waiting for you)"
    return f"#{r.id} [{r.status}] {r.topic}{extra}  ({r.evidence_count} supporting, last {r.last_seen_at:%Y-%m-%d})"


class InterestCommands:
    def __init__(self, service: InterestService) -> None:
        self._service = service
        self._store = service.store

    async def handle(self, line: str, read: Callable[[str], Awaitable[str]]) -> list[str] | None:
        line = line.strip()
        if not line.startswith("/"):
            return None
        command, _, rest = line[1:].partition(" ")
        if command.lower() != "interests":
            return None
        sub, _, arg = rest.strip().partition(" ")
        arg = arg.strip()
        sub = sub.lower()
        if sub == "":
            rows = [r for r in self._store.list() if r.status != "superseded"]
            return [_describe(r) for r in rows] or ["Nothing yet. Tell me what you're into with /interests add."]
        if sub == "add":
            row = self._service.add(arg)
            return [f"Added: #{row.id} {row.topic}"] if row else ["Usage: /interests add <a few words>"]
        if sub == "reflect":
            return await self._reflect()
        if sub == "forget" and arg.lower() == "all":
            return [f"Deleted {self._store.forget_all()} interest(s) and the run history."]
        if sub in ("why", "history", "approve", "reject", "mute", "forget"):
            ident = arg.lstrip("#")
            if not ident.isdigit():
                return [f"Usage: /interests {sub} <id>"]
            return self._by_id(sub, int(ident))
        return HELP

    def _by_id(self, sub: str, interest_id: int) -> list[str]:
        row = self._store.get(interest_id)
        if row is None:
            return [f"There is no interest #{interest_id}."]
        if sub == "why":
            ev = self._store.evidence(interest_id)
            return [f"#{row.id} {row.topic}"] + (
                [f"  {e.ts:%Y-%m-%d}: \"{e.quote}\"" for e in ev] or ["  (you told me directly)"]
            )
        if sub == "history":
            return [_describe(r) for r in self._store.history(interest_id)]
        if sub == "approve":
            ok = self._store.approve(interest_id, self._service._now())
            return [f"Kept: {row.topic}"] if ok else ["That isn't waiting for approval."]
        if sub == "reject":
            return [f"Declined: {row.topic}"] if self._store.reject(interest_id) else ["That isn't waiting for approval."]
        if sub == "mute":
            return [f"Muted: {row.topic}"] if self._store.mute(interest_id) else ["Only active or suggested interests can be muted."]
        return [f"Deleted #{interest_id} and its evidence."] if self._store.forget(interest_id) else ["Nothing deleted."]

    async def _reflect(self) -> list[str]:
        if not self._service.can_reflect:
            return ["Reflection is off (SUTRA_REFLECTION=off, or memory is off)."]
        try:
            result = await self._service.reflect_now()
        except Exception as exc:
            return [f"Reflection failed ({type(exc).__name__}); nothing was changed."]
        assert result is not None
        if result.skipped:
            return [f"Nothing to do: {result.skipped}."]
        return [f"Read {result.read} things you said and found {result.created} new suggestion(s)."]
