"""The fact bank: short pieces of the user's own recent words, and which have already been used."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .db import open_auth

AUTH_DB = "auth.db"
RETENTION = timedelta(days=7)
MAX_FACTS = 300


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


@dataclass(frozen=True)
class Fact:
    ref: str
    text: str
    kind: str  # "typed", "spoken", "reminder" or "plan"
    ts: datetime


class AuthStore:
    def __init__(self, directory: str | Path) -> None:
        self._conn = open_auth(Path(directory) / AUTH_DB)

    def close(self) -> None:
        self._conn.close()

    def add_fact(self, text: str, kind: str, ts: datetime) -> None:
        with self._conn:
            cur = self._conn.execute("INSERT INTO facts (ref, text, kind, ts) VALUES ('', ?, ?, ?)", (text, kind, _iso(ts)))
            self._conn.execute("UPDATE facts SET ref = ? WHERE id = ?", (f"turn:{cur.lastrowid}", cur.lastrowid))
            self._conn.execute(
                "DELETE FROM facts WHERE id NOT IN (SELECT id FROM facts ORDER BY id DESC LIMIT ?)", (MAX_FACTS,)
            )

    def facts(self, now: datetime) -> list[Fact]:
        """Recent facts that have not been used, newest first."""
        cutoff = _iso(now - RETENTION)
        with self._conn:
            self._conn.execute("DELETE FROM facts WHERE ts < ?", (cutoff,))
            self._conn.execute("DELETE FROM burned WHERE ts < ?", (_iso(now - 2 * RETENTION),))
        rows = self._conn.execute(
            "SELECT * FROM facts WHERE ref NOT IN (SELECT ref FROM burned) ORDER BY ts DESC"
        ).fetchall()
        return [Fact(r["ref"], r["text"], r["kind"], datetime.fromisoformat(r["ts"])) for r in rows]

    def burn(self, ref: str, now: datetime) -> None:
        with self._conn:
            self._conn.execute("INSERT OR IGNORE INTO burned (ref, ts) VALUES (?, ?)", (ref, _iso(now)))

    def is_burned(self, ref: str) -> bool:
        return self._conn.execute("SELECT 1 FROM burned WHERE ref = ?", (ref,)).fetchone() is not None

    def get_meta(self, key: str) -> str | None:
        row = self._conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else None

    def set_meta(self, key: str, value: str) -> None:
        with self._conn:
            self._conn.execute(
                "INSERT INTO meta (key, value) VALUES (?, ?)"
                " ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, value))

    def forget_all(self) -> int:
        with self._conn:
            n = self._conn.execute("SELECT COUNT(*) FROM facts").fetchone()[0]
            self._conn.execute("DELETE FROM facts")
            self._conn.execute("DELETE FROM burned")
            self._conn.execute("DELETE FROM meta WHERE key NOT IN ('enabled')")
        return n
