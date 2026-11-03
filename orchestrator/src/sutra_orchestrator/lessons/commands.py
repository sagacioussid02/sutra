"""REPL commands for lessons."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from .service import LessonService
from .store import Lesson

HELP = [
    "Lesson commands:",
    "  /lessons                list what I've learned and what I'm suggesting",
    "  /lessons why <id>       the things that led to it",
    "  /lessons approve <id>   agree to a suggestion",
    "  /lessons reject <id>    decline a suggestion (it won't come back)",
    "  /lessons retire <id>    stop following a lesson",
    "  /lessons history <id>   how a lesson was revised",
    "  /lessons forget <id>    delete it and its evidence",
    "  /lessons forget all     delete everything",
    "  /lessons reflect        look for lessons now",
    "  /lessons recheck        retry the safety check for approved lessons",
]


def _line(l: Lesson) -> str:
    notes = []
    if l.status in ("approved", "blocked") and l.reason:
        notes.append(l.reason)
    if l.not_working:
        notes.append(f"not working: you corrected this again {l.recurrences} time(s)")
    extra = f" ({'; '.join(notes)})" if notes else ""
    return f"#{l.id} [{l.status}] {l.text}{extra}"


class LessonCommands:
    def __init__(self, service: LessonService) -> None:
        self._service = service
        self._store = service.store

    async def handle(self, line: str, read: Callable[[str], Awaitable[str]]) -> list[str] | None:
        line = line.strip()
        if not line.startswith("/"):
            return None
        command, _, rest = line[1:].partition(" ")
        if command.lower() != "lessons":
            return None
        sub, _, arg = rest.strip().partition(" ")
        sub, arg = sub.lower(), arg.strip()
        if sub == "":
            rows = [l for l in self._store.list() if l.status != "superseded"]
            return [_line(l) for l in rows] or ["Nothing yet. I suggest lessons when I notice a pattern."]
        if sub == "reflect":
            return await self._reflect()
        if sub == "recheck":
            results = await self._service.recheck()
            return [f"#{i}: {r}" for i, r in results] or ["Nothing is waiting for a check."]
        if sub == "forget" and arg.lower() == "all":
            return [f"Deleted {self._store.forget_all()} lesson(s)."]
        if sub in ("why", "approve", "reject", "retire", "history", "forget"):
            ident = arg.lstrip("#")
            if not ident.isdigit():
                return [f"Usage: /lessons {sub} <id>"]
            return self._by_id(sub, int(ident))
        return HELP

    def _by_id(self, sub: str, lesson_id: int) -> list[str]:
        lesson = self._store.get(lesson_id)
        if lesson is None:
            return [f"There is no lesson #{lesson_id}."]
        if sub == "why":
            ev = self._store.evidence(lesson_id)
            return [_line(lesson)] + ([f"  {t:%Y-%m-%d}: \"{q}\"" for q, t in ev] or ["  (no evidence recorded)"])
        if sub == "history":
            return [_line(l) for l in self._store.history(lesson_id)]
        if sub == "approve":
            return [self._service.approve(lesson_id)]
        if sub == "reject":
            return [self._service.reject(lesson_id)]
        if sub == "retire":
            return [self._service.retire(lesson_id)]
        return [f"Deleted #{lesson_id} and its evidence."] if self._store.forget(lesson_id) else ["Nothing deleted."]

    async def _reflect(self) -> list[str]:
        if not self._service.can_reflect:
            return ["Reflection is off (SUTRA_LESSONS_REFLECTION=off)."]
        try:
            result = await self._service.reflect_now()
        except Exception as exc:
            return [f"Reflection failed ({type(exc).__name__}); nothing was changed."]
        assert result is not None
        if result.skipped and not result.created:
            return [f"Nothing new to look at: {result.skipped}."]
        return [f"Looked at {result.read} exchanges and found {result.created} new suggestion(s)."]
