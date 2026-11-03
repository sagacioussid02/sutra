"""The life store: people the user mentions and things they have coming up."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

from ..interests.reflect import similar
from .db import open_life

LIFE_DB = "life.db"
MAX_PEOPLE = 200
MAX_UPCOMING = 100


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def _parse(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


@dataclass(frozen=True)
class Person:
    id: int
    name: str
    relation: str
    first_seen: datetime
    last_mentioned: datetime
    mentions: int


@dataclass(frozen=True)
class Plan:
    id: int
    text: str
    who: str
    when_date: date | None
    status: str
    created_at: datetime
    asked_at: datetime | None
    retry_after: datetime | None


def _person(r: sqlite3.Row) -> Person:
    return Person(r["id"], r["name"], r["relation"], datetime.fromisoformat(r["first_seen"]),
                  datetime.fromisoformat(r["last_mentioned"]), r["mentions"])


def _plan(r: sqlite3.Row) -> Plan:
    return Plan(r["id"], r["text"], r["who"], date.fromisoformat(r["when_date"]) if r["when_date"] else None,
                r["status"], datetime.fromisoformat(r["created_at"]), _parse(r["asked_at"]), _parse(r["retry_after"]))


class LifeStore:
    def __init__(self, directory: str | Path) -> None:
        self._conn = open_life(Path(directory) / LIFE_DB)

    def close(self) -> None:
        self._conn.close()

    # ----------------------------------------------------------------- people

    def add_person(self, name: str, relation: str, now: datetime) -> int | None:
        """A new person, or the existing one with another mention. None if the list is full."""
        row = self._conn.execute("SELECT * FROM people WHERE name = ? COLLATE NOCASE", (name,)).fetchone()
        with self._conn:
            if row is not None:
                keep = relation if relation and not row["relation"] else row["relation"]
                self._conn.execute(
                    "UPDATE people SET relation = ?, last_mentioned = ?, mentions = mentions + 1 WHERE id = ?",
                    (keep, _iso(now), row["id"]),
                )
                return int(row["id"])
            if self._conn.execute("SELECT COUNT(*) FROM people").fetchone()[0] >= MAX_PEOPLE:
                return None
            cur = self._conn.execute(
                "INSERT INTO people (name, relation, first_seen, last_mentioned) VALUES (?, ?, ?, ?)",
                (name, relation, _iso(now), _iso(now)),
            )
        return int(cur.lastrowid)

    def people(self) -> list[Person]:
        return [_person(r) for r in self._conn.execute("SELECT * FROM people ORDER BY last_mentioned DESC")]

    def get_person(self, person_id: int) -> Person | None:
        row = self._conn.execute("SELECT * FROM people WHERE id = ?", (person_id,)).fetchone()
        return _person(row) if row else None

    # ------------------------------------------------------------------ plans

    def add_plan(self, text: str, who: str, when_date: date | None, now: datetime) -> int | None:
        """A new plan unless a similar one on the same date exists. None if skipped or the list is full."""
        for p in self.plans(("upcoming", "asked")):
            if p.when_date == when_date and (similar(text, p.text) or similar(p.text, text)):
                return None
        if len(self.plans(("upcoming",))) >= MAX_UPCOMING:
            return None
        with self._conn:
            cur = self._conn.execute(
                "INSERT INTO plans (text, who, when_date, status, created_at) VALUES (?, ?, ?, 'upcoming', ?)",
                (text, who, when_date.isoformat() if when_date else None, _iso(now)),
            )
        return int(cur.lastrowid)

    def plans(self, statuses: tuple[str, ...] | None = None) -> list[Plan]:
        if statuses:
            marks = ",".join("?" * len(statuses))
            rows = self._conn.execute(f"SELECT * FROM plans WHERE status IN ({marks}) ORDER BY when_date, id", statuses)
        else:
            rows = self._conn.execute("SELECT * FROM plans ORDER BY id DESC LIMIT 100")
        return [_plan(r) for r in rows]

    def get_plan(self, plan_id: int) -> Plan | None:
        row = self._conn.execute("SELECT * FROM plans WHERE id = ?", (plan_id,)).fetchone()
        return _plan(row) if row else None

    def set_plan(self, plan_id: int, status: str, *, asked_at: datetime | None = None,
                 retry_after: datetime | None = None) -> None:
        with self._conn:
            self._conn.execute(
                "UPDATE plans SET status = ?, asked_at = COALESCE(?, asked_at), retry_after = ? WHERE id = ?",
                (status, _iso(asked_at) if asked_at else None, _iso(retry_after) if retry_after else None, plan_id),
            )

    # -------------------------------------------------------------- meta, wipe

    def get_meta(self, key: str) -> str | None:
        row = self._conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else None

    def set_meta(self, key: str, value: str) -> None:
        with self._conn:
            self._conn.execute(
                "INSERT INTO meta (key, value) VALUES (?, ?)"
                " ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, value))

    def forget_person(self, person_id: int) -> bool:
        with self._conn:
            return self._conn.execute("DELETE FROM people WHERE id = ?", (person_id,)).rowcount > 0

    def forget_plan(self, plan_id: int) -> bool:
        with self._conn:
            return self._conn.execute("DELETE FROM plans WHERE id = ?", (plan_id,)).rowcount > 0

    def forget_all(self) -> tuple[int, int]:
        with self._conn:
            p = self._conn.execute("SELECT COUNT(*) FROM people").fetchone()[0]
            q = self._conn.execute("SELECT COUNT(*) FROM plans").fetchone()[0]
            for table in ("people", "plans", "meta"):
                self._conn.execute(f"DELETE FROM {table}")
        return p, q
