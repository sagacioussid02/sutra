"""The idle research record: what was looked into, when, and how it ended."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .db import open_idle

IDLE_DB = "idle.db"
FINDINGS_CHARS = 4000
RAN = ("running", "done", "partial", "empty", "failed", "interrupted")  # outcomes that used a run


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def _parse(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


@dataclass(frozen=True)
class IdleRun:
    id: int
    topic: str
    brief: str
    kind: str
    outcome: str
    findings: str
    summary: str
    signal_id: int | None
    created_at: datetime
    not_before: datetime | None


def _run(r: sqlite3.Row) -> IdleRun:
    return IdleRun(
        id=r["id"], topic=r["topic"], brief=r["brief"], kind=r["kind"], outcome=r["outcome"],
        findings=r["findings"], summary=r["summary"], signal_id=r["signal_id"],
        created_at=datetime.fromisoformat(r["created_at"]), not_before=_parse(r["not_before"]),
    )


class IdleStore:
    def __init__(self, directory: str | Path) -> None:
        self._conn = open_idle(Path(directory) / IDLE_DB)
        with self._conn:  # a run still 'running' belongs to a process that ended without finishing it
            self._conn.execute("UPDATE runs SET outcome = 'interrupted' WHERE outcome = 'running'")

    def close(self) -> None:
        self._conn.close()

    def add_run(
        self, topic: str, brief: str, kind: str, outcome: str, now: datetime,
        *, not_before: datetime | None = None,
    ) -> int:
        with self._conn:
            cur = self._conn.execute(
                "INSERT INTO runs (topic, brief, kind, outcome, created_at, not_before)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (topic, brief, kind, outcome, _iso(now), _iso(not_before) if not_before else None),
            )
        return int(cur.lastrowid)

    def finish(
        self, run_id: int, outcome: str, *, findings: str = "", summary: str = "",
        signal_id: int | None = None,
    ) -> None:
        """Close a run. Only a run that produced something keeps its revisit delay: a failed,
        empty or interrupted one learned nothing, so the topic may be tried again."""
        keep = outcome in ("done", "partial")
        with self._conn:
            self._conn.execute(
                "UPDATE runs SET outcome = ?, findings = ?, summary = ?, signal_id = ?,"
                " not_before = CASE WHEN ? THEN not_before ELSE NULL END WHERE id = ?",
                (outcome, findings[:FINDINGS_CHARS], summary, signal_id, int(keep), run_id),
            )

    def get(self, run_id: int) -> IdleRun | None:
        row = self._conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
        return _run(row) if row else None

    def recent(self, limit: int = 10) -> list[IdleRun]:
        rows = self._conn.execute("SELECT * FROM runs ORDER BY id DESC LIMIT ?", (limit,))
        return [_run(r) for r in rows]

    def ran_since(self, since: datetime) -> int:
        marks = ",".join("?" * len(RAN))
        return self._conn.execute(
            f"SELECT COUNT(*) FROM runs WHERE created_at >= ? AND outcome IN ({marks})",
            (_iso(since), *RAN),
        ).fetchone()[0]

    def last_ran(self) -> datetime | None:
        marks = ",".join("?" * len(RAN))
        row = self._conn.execute(
            f"SELECT created_at FROM runs WHERE outcome IN ({marks}) ORDER BY id DESC LIMIT 1", RAN
        ).fetchone()
        return _parse(row["created_at"]) if row else None

    def get_meta(self, key: str) -> str | None:
        row = self._conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else None

    def set_meta(self, key: str, value: str) -> None:
        with self._conn:
            self._conn.execute(
                "INSERT INTO meta (key, value) VALUES (?, ?)"
                " ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )

    def forget_all(self) -> int:
        with self._conn:
            n = self._conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
            self._conn.execute("DELETE FROM runs")
            self._conn.execute("DELETE FROM meta WHERE key != 'enabled'")
        return n
