"""The run record: what was asked, what it cost, what came back."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .db import open_agents
from .types import Findings, Source

AGENTS_DB = "agents.db"


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


@dataclass(frozen=True)
class RunRow:
    id: int
    task: str
    status: str
    created_at: datetime
    finished_at: datetime | None
    searches: int
    tool_calls: int
    output_tokens: int
    reason: str
    findings: str
    sources: list[Source]


def _row(r: sqlite3.Row) -> RunRow:
    return RunRow(
        id=r["id"],
        task=r["task"],
        status=r["status"],
        created_at=datetime.fromisoformat(r["created_at"]),
        finished_at=datetime.fromisoformat(r["finished_at"]) if r["finished_at"] else None,
        searches=r["searches"],
        tool_calls=r["tool_calls"],
        output_tokens=r["output_tokens"],
        reason=r["reason"],
        findings=r["findings"],
        sources=[Source(**s) for s in json.loads(r["sources"])],
    )


class AgentStore:
    def __init__(self, directory: str | Path) -> None:
        self._conn = open_agents(Path(directory) / AGENTS_DB)
        # A row still 'running' belongs to a process that ended without finishing it.
        with self._conn:
            self._conn.execute(
                "UPDATE runs SET status = 'interrupted' WHERE status = 'running'"
            )

    def start(self, task: str, now: datetime) -> int:
        with self._conn:
            cursor = self._conn.execute(
                "INSERT INTO runs (task, status, created_at) VALUES (?, 'running', ?)",
                (task, _iso(now)),
            )
        return int(cursor.lastrowid)

    def finish(self, run_id: int, findings: Findings, now: datetime, *, failed: bool = False) -> None:
        status = "failed" if failed else ("partial" if findings.partial else "done")
        with self._conn:
            self._conn.execute(
                "UPDATE runs SET status = ?, finished_at = ?, searches = ?, tool_calls = ?,"
                " output_tokens = ?, reason = ?, findings = ?, sources = ? WHERE id = ?",
                (
                    status,
                    _iso(now),
                    findings.searches,
                    findings.tool_calls,
                    findings.output_tokens,
                    findings.reason,
                    findings.text,
                    json.dumps([{"url": s.url, "title": s.title} for s in findings.sources]),
                    run_id,
                ),
            )

    def interrupt(self, run_id: int, now: datetime) -> None:
        with self._conn:
            self._conn.execute(
                "UPDATE runs SET status = 'interrupted', finished_at = ? WHERE id = ? AND status = 'running'",
                (_iso(now), run_id),
            )

    def get(self, run_id: int) -> RunRow | None:
        r = self._conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        return _row(r) if r else None

    def list_runs(self, limit: int = 20) -> list[RunRow]:
        rows = self._conn.execute("SELECT * FROM runs ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [_row(r) for r in rows]

    def usage_since(self, start: datetime) -> tuple[int, int]:
        """(runs started, output tokens used) since ``start``."""
        r = self._conn.execute(
            "SELECT COUNT(*) AS n, COALESCE(SUM(output_tokens), 0) AS t FROM runs WHERE created_at >= ?",
            (_iso(start),),
        ).fetchone()
        return int(r["n"]), int(r["t"])

    def purge(self) -> int:
        with self._conn:
            cursor = self._conn.execute("DELETE FROM runs")
        return cursor.rowcount

    def close(self) -> None:
        self._conn.close()
