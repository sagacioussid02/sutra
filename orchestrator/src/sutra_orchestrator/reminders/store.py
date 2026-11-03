"""The reminder store: durable SQLite CRUD plus the delivery inbox.

Firing is a claim, the same shape as the gateway's confirmation Claims:
a reminder moves ``pending -> fired`` in a single guarded UPDATE, and
only the caller whose update actually changed the row may deliver it.
Two scheduler loops (or a REPL and a voice process sharing the file) can
therefore never deliver the same reminder twice.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .db import open_reminders

REMINDERS_DB = "reminders.db"


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def _parse(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


@dataclass(frozen=True)
class ReminderRow:
    id: int
    text: str
    fire_at: datetime
    tz: str
    status: str
    created_at: datetime
    fired_at: datetime | None
    late: bool


@dataclass(frozen=True)
class InboxRow:
    id: int
    reminder_id: int
    text: str
    fire_at: datetime
    delivered_at: datetime
    late: bool
    seen: bool


def _reminder(r: sqlite3.Row) -> ReminderRow:
    return ReminderRow(
        id=r["id"],
        text=r["text"],
        fire_at=datetime.fromisoformat(r["fire_at"]),
        tz=r["tz"],
        status=r["status"],
        created_at=datetime.fromisoformat(r["created_at"]),
        fired_at=_parse(r["fired_at"]),
        late=bool(r["late"]),
    )


def _inbox(r: sqlite3.Row) -> InboxRow:
    return InboxRow(
        id=r["id"],
        reminder_id=r["reminder_id"],
        text=r["text"],
        fire_at=datetime.fromisoformat(r["fire_at"]),
        delivered_at=datetime.fromisoformat(r["delivered_at"]),
        late=bool(r["late"]),
        seen=bool(r["seen"]),
    )


class ReminderStore:
    def __init__(self, directory: str | Path) -> None:
        self._conn = open_reminders(Path(directory) / REMINDERS_DB)

    # ------------------------------------------------------------- reminders

    def add(self, text: str, fire_at: datetime, tz: str, created_at: datetime) -> ReminderRow:
        with self._conn:
            cursor = self._conn.execute(
                "INSERT INTO reminders (text, fire_at, tz, status, created_at)"
                " VALUES (?, ?, ?, 'pending', ?)",
                (text, _iso(fire_at), tz, _iso(created_at)),
            )
            row_id = cursor.lastrowid
        found = self.get(row_id)
        assert found is not None
        return found

    def get(self, reminder_id: int) -> ReminderRow | None:
        row = self._conn.execute(
            "SELECT * FROM reminders WHERE id = ?", (reminder_id,)
        ).fetchone()
        return _reminder(row) if row else None

    def list_pending(self) -> list[ReminderRow]:
        rows = self._conn.execute(
            "SELECT * FROM reminders WHERE status = 'pending' ORDER BY fire_at, id"
        ).fetchall()
        return [_reminder(r) for r in rows]

    def cancel(self, reminder_id: int) -> bool:
        """Cancel a pending reminder. False if it is not pending (or absent)."""
        with self._conn:
            cursor = self._conn.execute(
                "UPDATE reminders SET status = 'cancelled' WHERE id = ? AND status = 'pending'",
                (reminder_id,),
            )
        return cursor.rowcount == 1

    def due(self, now: datetime) -> list[ReminderRow]:
        rows = self._conn.execute(
            "SELECT * FROM reminders WHERE status = 'pending' AND fire_at <= ?"
            " ORDER BY fire_at, id",
            (_iso(now),),
        ).fetchall()
        return [_reminder(r) for r in rows]

    def claim(self, reminder_id: int, fired_at: datetime, *, late: bool) -> bool:
        """Atomically move one reminder pending -> fired.

        Returns True only for the caller that won the transition; that
        caller owns delivery. Everyone else gets False.
        """
        with self._conn:
            cursor = self._conn.execute(
                "UPDATE reminders SET status = 'fired', fired_at = ?, late = ?"
                " WHERE id = ? AND status = 'pending'",
                (_iso(fired_at), 1 if late else 0, reminder_id),
            )
        return cursor.rowcount == 1

    # ----------------------------------------------------------------- inbox

    def deliver(self, reminder: ReminderRow, delivered_at: datetime) -> InboxRow:
        """Put a fired reminder in the inbox. Call only after winning its claim."""
        with self._conn:
            cursor = self._conn.execute(
                "INSERT INTO inbox (reminder_id, text, fire_at, delivered_at, late)"
                " VALUES (?, ?, ?, ?, ?)",
                (
                    reminder.id,
                    reminder.text,
                    _iso(reminder.fire_at),
                    _iso(delivered_at),
                    1 if reminder.late else 0,
                ),
            )
            row_id = cursor.lastrowid
        row = self._conn.execute("SELECT * FROM inbox WHERE id = ?", (row_id,)).fetchone()
        return _inbox(row)

    def list_inbox(self, *, unseen_only: bool = False) -> list[InboxRow]:
        query = "SELECT * FROM inbox"
        if unseen_only:
            query += " WHERE seen = 0"
        query += " ORDER BY delivered_at, id"
        return [_inbox(r) for r in self._conn.execute(query).fetchall()]

    def mark_seen(self, inbox_id: int) -> bool:
        with self._conn:
            cursor = self._conn.execute(
                "UPDATE inbox SET seen = 1 WHERE id = ? AND seen = 0", (inbox_id,)
            )
        return cursor.rowcount == 1

    def close(self) -> None:
        self._conn.close()
