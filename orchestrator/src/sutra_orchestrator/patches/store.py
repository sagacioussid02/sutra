"""The patch record: what was asked, what came back, what it cost."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .db import open_patches

PATCHES_DB = "patches.db"


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


@dataclass(frozen=True)
class PatchRow:
    id: int
    task: str
    status: str
    created_at: datetime
    finished_at: datetime | None
    branch: str
    tool_calls: int
    output_tokens: int
    reason: str
    summary: str
    files: list[str]
    refusals: int
    test_status: str
    test_detail: str
    diff_stat: str


def _row(r: sqlite3.Row) -> PatchRow:
    return PatchRow(
        id=r["id"], task=r["task"], status=r["status"],
        created_at=datetime.fromisoformat(r["created_at"]),
        finished_at=datetime.fromisoformat(r["finished_at"]) if r["finished_at"] else None,
        branch=r["branch"], tool_calls=r["tool_calls"], output_tokens=r["output_tokens"],
        reason=r["reason"], summary=r["summary"], files=json.loads(r["files"]),
        refusals=r["refusals"], test_status=r["test_status"], test_detail=r["test_detail"],
        diff_stat=r["diff_stat"],
    )


class PatchStore:
    def __init__(self, directory: str | Path) -> None:
        self._conn = open_patches(Path(directory) / PATCHES_DB)
        with self._conn:
            self._conn.execute("UPDATE patches SET status = 'interrupted' WHERE status = 'running'")

    def start(self, task: str, now: datetime) -> int:
        with self._conn:
            cur = self._conn.execute(
                "INSERT INTO patches (task, status, created_at) VALUES (?, 'running', ?)",
                (task, _iso(now)),
            )
        return int(cur.lastrowid)

    def set_branch(self, pid: int, branch: str) -> None:
        with self._conn:
            self._conn.execute("UPDATE patches SET branch = ? WHERE id = ?", (branch, pid))

    def finish(
        self, pid: int, status: str, now: datetime, *, tool_calls: int = 0, output_tokens: int = 0,
        reason: str = "", summary: str = "", files: list[str] | None = None, refusals: int = 0,
        test_status: str = "untested", test_detail: str = "", diff_stat: str = "",
    ) -> None:
        with self._conn:
            self._conn.execute(
                "UPDATE patches SET status = ?, finished_at = ?, tool_calls = ?, output_tokens = ?,"
                " reason = ?, summary = ?, files = ?, refusals = ?, test_status = ?, test_detail = ?,"
                " diff_stat = ? WHERE id = ?",
                (status, _iso(now), tool_calls, output_tokens, reason, summary,
                 json.dumps(files or []), refusals, test_status, test_detail, diff_stat, pid),
            )

    def interrupt(self, pid: int, now: datetime) -> None:
        with self._conn:
            self._conn.execute(
                "UPDATE patches SET status = 'interrupted', finished_at = ? WHERE id = ? AND status = 'running'",
                (_iso(now), pid),
            )

    def mark_discarded(self, pid: int) -> None:
        with self._conn:
            self._conn.execute("UPDATE patches SET status = 'discarded' WHERE id = ?", (pid,))

    def get(self, pid: int) -> PatchRow | None:
        r = self._conn.execute("SELECT * FROM patches WHERE id = ?", (pid,)).fetchone()
        return _row(r) if r else None

    def list_patches(self, limit: int = 20, *, include_discarded: bool = False) -> list[PatchRow]:
        where = "" if include_discarded else "WHERE status != 'discarded'"
        rows = self._conn.execute(
            f"SELECT * FROM patches {where} ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [_row(r) for r in rows]

    def usage_since(self, start: datetime) -> tuple[int, int]:
        r = self._conn.execute(
            "SELECT COUNT(*) AS n, COALESCE(SUM(output_tokens), 0) AS t FROM patches WHERE created_at >= ?",
            (_iso(start),),
        ).fetchone()
        return int(r["n"]), int(r["t"])

    def close(self) -> None:
        self._conn.close()
