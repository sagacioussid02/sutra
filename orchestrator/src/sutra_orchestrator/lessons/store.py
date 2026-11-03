"""The lesson store: proposals, their status and evidence."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .db import open_lessons

LESSONS_DB = "lessons.db"
QUOTE_CHARS = 120
STATUSES = ("proposed", "approved", "active", "rejected", "retired", "superseded", "blocked")


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def _parse(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


@dataclass(frozen=True)
class Lesson:
    id: int
    text: str
    effect: str  # "guidance" or "block"
    kind: str  # for a block: the offer kind, or "" for any
    topic: str  # for a block: the topic, or "" for the whole kind
    status: str
    source: str
    revises_id: int | None
    reason: str
    not_working: bool
    recurrences: int
    asked_at: datetime | None
    created_at: datetime
    updated_at: datetime


def _lesson(r: sqlite3.Row) -> Lesson:
    return Lesson(
        id=r["id"], text=r["text"], effect=r["effect"], kind=r["kind"], topic=r["topic"],
        status=r["status"], source=r["source"], revises_id=r["revises_id"], reason=r["reason"],
        not_working=bool(r["not_working"]), recurrences=r["recurrences"],
        asked_at=_parse(r["asked_at"]), created_at=datetime.fromisoformat(r["created_at"]),
        updated_at=datetime.fromisoformat(r["updated_at"]),
    )


class LessonStore:
    def __init__(self, directory: str | Path) -> None:
        self._conn = open_lessons(Path(directory) / LESSONS_DB)

    def close(self) -> None:
        self._conn.close()

    def add(
        self, text: str, effect: str, source: str, now: datetime, *, kind: str = "", topic: str = "",
        revises_id: int | None = None,
    ) -> int:
        """A new lesson is always a proposal: it has no effect until the user says so."""
        with self._conn:
            cur = self._conn.execute(
                "INSERT INTO lessons (text, effect, kind, topic, status, source, revises_id, created_at,"
                " updated_at) VALUES (?, ?, ?, ?, 'proposed', ?, ?, ?, ?)",
                (text, effect, kind, topic, source, revises_id, _iso(now), _iso(now)),
            )
        return int(cur.lastrowid)

    def get(self, lesson_id: int) -> Lesson | None:
        row = self._conn.execute("SELECT * FROM lessons WHERE id = ?", (lesson_id,)).fetchone()
        return _lesson(row) if row else None

    def list(self, statuses: tuple[str, ...] | None = None) -> list[Lesson]:
        if statuses:
            marks = ",".join("?" * len(statuses))
            rows = self._conn.execute(
                f"SELECT * FROM lessons WHERE status IN ({marks}) ORDER BY id", statuses
            )
        else:
            rows = self._conn.execute("SELECT * FROM lessons ORDER BY id")
        return [_lesson(r) for r in rows]

    def set_status(self, lesson_id: int, status: str, now: datetime, reason: str = "") -> None:
        assert status in STATUSES, status
        with self._conn:
            self._conn.execute(
                "UPDATE lessons SET status = ?, reason = ?, updated_at = ? WHERE id = ?",
                (status, reason, _iso(now), lesson_id),
            )

    def mark_asked(self, lesson_id: int, now: datetime) -> None:
        with self._conn:
            self._conn.execute("UPDATE lessons SET asked_at = ? WHERE id = ?", (_iso(now), lesson_id))

    def record_recurrence(self, lesson_id: int) -> None:
        with self._conn:
            self._conn.execute(
                "UPDATE lessons SET recurrences = recurrences + 1, not_working = 1 WHERE id = ?",
                (lesson_id,),
            )

    def add_evidence(self, lesson_id: int, ref: str, quote: str, ts: datetime) -> bool:
        quote = " ".join(quote.split())[:QUOTE_CHARS]
        with self._conn:
            cur = self._conn.execute(
                "INSERT OR IGNORE INTO evidence (lesson_id, ref, quote, ts) VALUES (?, ?, ?, ?)",
                (lesson_id, ref, quote, _iso(ts)),
            )
        return cur.rowcount > 0

    def evidence(self, lesson_id: int) -> list[tuple[str, datetime]]:
        rows = self._conn.execute(
            "SELECT quote, ts FROM evidence WHERE lesson_id = ? ORDER BY ts", (lesson_id,)
        )
        return [(r["quote"], datetime.fromisoformat(r["ts"])) for r in rows]

    def history(self, lesson_id: int) -> list[Lesson]:
        """The lesson and every revision chained to it, oldest first."""
        chain: list[Lesson] = []
        current = self.get(lesson_id)
        while current is not None and current.id not in {c.id for c in chain}:
            chain.append(current)
            current = self.get(current.revises_id) if current.revises_id else None
        return list(reversed(chain))

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

    def forget(self, lesson_id: int) -> bool:
        with self._conn:
            self._conn.execute("DELETE FROM evidence WHERE lesson_id = ?", (lesson_id,))
            cur = self._conn.execute("DELETE FROM lessons WHERE id = ?", (lesson_id,))
        return cur.rowcount > 0

    def forget_all(self) -> int:
        with self._conn:
            n = self._conn.execute("SELECT COUNT(*) FROM lessons").fetchone()[0]
            self._conn.execute("DELETE FROM evidence")
            self._conn.execute("DELETE FROM lessons")
            self._conn.execute("DELETE FROM meta")
        return n
