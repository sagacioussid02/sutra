"""The event log: append, drain after a cursor, advance, expire."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .db import open_events
from .kinds import Event

EVENTS_DB = "events.db"


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def _event(r: sqlite3.Row) -> Event:
    return Event(
        id=r["id"], source=r["source"], kind=r["kind"],
        occurred_at=datetime.fromisoformat(r["occurred_at"]), received_at=datetime.fromisoformat(r["received_at"]),
        user_id=r["user_id"], payload=json.loads(r["payload"]), idempotency_key=r["idempotency_key"],
        expires_at=datetime.fromisoformat(r["expires_at"]), seq=r["seq"],
    )


class EventStore:
    def __init__(self, directory: Path) -> None:
        self._db = open_events(directory / EVENTS_DB)

    def close(self) -> None:
        self._db.close()

    def append(self, e: Event) -> bool:
        """Store an event. False if it is a duplicate (same id, or same source + idempotency key)."""
        try:
            with self._db:
                self._db.execute(
                    "INSERT INTO events (id, source, kind, occurred_at, received_at, user_id, payload,"
                    " idempotency_key, expires_at) VALUES (?,?,?,?,?,?,?,?,?)",
                    (e.id, e.source, e.kind, _iso(e.occurred_at), _iso(e.received_at), e.user_id,
                     json.dumps(e.payload), e.idempotency_key, _iso(e.expires_at)),
                )
        except sqlite3.IntegrityError:
            return False
        return True

    def count(self) -> int:
        return self._db.execute("SELECT COUNT(*) FROM events").fetchone()[0]

    def cursor(self, consumer: str) -> int:
        row = self._db.execute("SELECT last_seq FROM cursors WHERE consumer = ?", (consumer,)).fetchone()
        return row["last_seq"] if row else 0

    def drain(self, consumer: str, kinds: tuple[str, ...], now: datetime, limit: int) -> list[Event]:
        """Unexpired events of these kinds after the consumer's cursor, in receive order."""
        marks = ",".join("?" for _ in kinds)
        rows = self._db.execute(
            f"SELECT * FROM events WHERE seq > ? AND expires_at > ? AND kind IN ({marks}) ORDER BY seq LIMIT ?",
            (self.cursor(consumer), _iso(now), *kinds, limit),
        ).fetchall()
        return [_event(r) for r in rows]

    def advance(self, consumer: str, seq: int) -> None:
        with self._db:
            self._db.execute(
                "INSERT INTO cursors (consumer, last_seq) VALUES (?, ?)"
                " ON CONFLICT(consumer) DO UPDATE SET last_seq = MAX(last_seq, excluded.last_seq)",
                (consumer, seq),
            )
            self._db.execute("DELETE FROM attempts WHERE consumer = ? AND seq <= ?", (consumer, seq))

    def was_handled(self, consumer: str, event_id: str) -> bool:
        return self._db.execute(
            "SELECT 1 FROM handled WHERE consumer = ? AND event_id = ?", (consumer, event_id)
        ).fetchone() is not None

    def mark_handled(self, consumer: str, event_id: str) -> None:
        with self._db:
            self._db.execute("INSERT OR IGNORE INTO handled (consumer, event_id) VALUES (?, ?)", (consumer, event_id))

    def record_failure(self, consumer: str, seq: int, error: str) -> int:
        with self._db:
            self._db.execute(
                "INSERT INTO attempts (consumer, seq, failures, last_error) VALUES (?, ?, 1, ?)"
                " ON CONFLICT(consumer, seq) DO UPDATE SET failures = failures + 1, last_error = excluded.last_error",
                (consumer, seq, error[:200]),
            )
        return self._db.execute(
            "SELECT failures FROM attempts WHERE consumer = ? AND seq = ?", (consumer, seq)
        ).fetchone()[0]

    def record_skip(self, consumer: str, seq: int, error: str, now: datetime) -> None:
        with self._db:
            self._db.execute(
                "INSERT OR REPLACE INTO skipped (consumer, seq, error, at) VALUES (?, ?, ?, ?)",
                (consumer, seq, error[:200], _iso(now)),
            )

    def skipped(self) -> list[sqlite3.Row]:
        return self._db.execute("SELECT * FROM skipped ORDER BY at DESC LIMIT 20").fetchall()

    def sweep(self, now: datetime, retention_cutoff: datetime) -> int:
        """Delete expired events, and anything older than the retention period."""
        with self._db:
            cur = self._db.execute(
                "DELETE FROM events WHERE expires_at <= ? OR received_at <= ?", (_iso(now), _iso(retention_cutoff))
            )
            self._db.execute("DELETE FROM handled WHERE event_id NOT IN (SELECT id FROM events)")
        return cur.rowcount

    def recent(self, limit: int) -> list[Event]:
        rows = self._db.execute("SELECT * FROM events ORDER BY seq DESC LIMIT ?", (limit,)).fetchall()
        return [_event(r) for r in rows]

    def per_source(self) -> list[tuple[str, int]]:
        rows = self._db.execute("SELECT source, COUNT(*) n FROM events GROUP BY source ORDER BY n DESC").fetchall()
        return [(r["source"], r["n"]) for r in rows]

    def cursors(self) -> dict[str, int]:
        return {r["consumer"]: r["last_seq"] for r in self._db.execute("SELECT * FROM cursors")}
