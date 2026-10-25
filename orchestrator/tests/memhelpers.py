"""Shared helpers for the memory tests."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sutra_orchestrator.memory import Episode, ToolCallRecord
from sutra_orchestrator.memstore import SqliteMemory

from .fakes import Clock


def stmt(content: str, spoken: str | None = None, kind: str = "fact") -> dict[str, str]:
    return {"content": content, "spoken": spoken or content, "kind": kind}


class FakeExtractor:
    """Returns scripted statements keyed on text in the *current* user message."""

    def __init__(self, results: dict[str, list[dict[str, Any]]] | None = None):
        self.results = results or {}
        self.calls: list[dict[str, str]] = []
        self.error: Exception | None = None
        self.raw: Any = None

    async def extract(self, *, system: str, user: str) -> Any:
        self.calls.append({"system": system, "user": user})
        if self.error is not None:
            raise self.error
        if self.raw is not None:
            return self.raw
        current = user.split("Their current message:\n", 1)[-1]
        for needle, statements in self.results.items():
            if needle in current:
                return statements
        return []


def make_memory(
    tmp_path: Path,
    extractor: FakeExtractor | None = None,
    clock: Clock | None = None,
    notices: list[str] | None = None,
    **kwargs: Any,
) -> SqliteMemory:
    return SqliteMemory(
        tmp_path / "data",
        extractor=extractor,
        now=clock or Clock(),
        on_notice=notices.append if notices is not None else None,
        **kwargs,
    )


async def run_turn(
    memory: SqliteMemory,
    utterance: str,
    reply: str = "ok",
    tools: tuple[ToolCallRecord, ...] = (),
    confirmation: str | None = None,
    clock: Clock | None = None,
):
    """Drive one turn the way the orchestrator does: recall, then record, then settle."""
    items = await memory.recall(utterance)
    await memory.record(
        Episode(
            utterance=utterance,
            reply=reply,
            tools=tools,
            confirmation=confirmation,
            timestamp=clock() if clock else None,
        )
    )
    await memory.flush()
    return items
