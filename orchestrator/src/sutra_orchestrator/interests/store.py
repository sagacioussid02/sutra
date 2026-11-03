"""The interest profile store: topics, their evidence, and how they changed."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .db import open_interests

INTERESTS_DB = "interests.db"
QUOTE_CHARS = 120


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def _parse(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


@dataclass(frozen=True)
class InterestRow:
    id: int
    topic: str
    status: str
    source: str
    created_at: datetime
    last_seen_at: datetime
    revises_id: int | None
    change_before: str | None
    change_now: str | None
    offer: str | None
    offered_at: datetime | None
    checkin: str | None
    evidence_count: int


@dataclass(frozen=True)
class EvidenceRow:
    interest_id: int
    episode_id: str
    quote: str
    ts: datetime


_SELECT = (
    "SELECT i.*, (SELECT COUNT(*) FROM evidence e WHERE e.interest_id = i.id) AS evidence_count"
    " FROM interests i"
)


def _row(r: sqlite3.Row) -> InterestRow:
    return InterestRow(
        id=r["id"],
        topic=r["topic"],
        status=r["status"],
        source=r["source"],
        created_at=datetime.fromisoformat(r["created_at"]),
        last_seen_at=datetime.fromisoformat(r["last_seen_at"]),
        revises_id=r["revises_id"],
        change_before=r["change_before"],
        change_now=r["change_now"],
        offer=r["offer"],
        offered_at=_parse(r["offered_at"]),
        checkin=r["checkin"],
        evidence_count=r["evidence_count"],
    )


class InterestStore:
    def __init__(self, directory: str | Path) -> None:
        self._conn = open_interests(Path(directory) / INTERESTS_DB)

    # ------------------------------------------------------------- interests

    def add(
        self,
        topic: str,
        *,
        status: str,
        source: str,
        now: datetime,
        revises_id: int | None = None,
        change_before: str | None = None,
        change_now: str | None = None,
        offer: bool = False,
    ) -> int:
        with self._conn:
            cursor = self._conn.execute(
                "INSERT INTO interests (topic, status, source, created_at, last_seen_at,"
                " revises_id, change_before, change_now, offer) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    topic,
                    status,
                    source,
                    _iso(now),
                    _iso(now),
                    revises_id,
                    change_before,
                    change_now,
                    "pending" if offer else None,
                ),
            )
        return int(cursor.lastrowid)

    def get(self, interest_id: int) -> InterestRow | None:
        r = self._conn.execute(_SELECT + " WHERE i.id = ?", (interest_id,)).fetchone()
        return _row(r) if r else None

    def list(self, statuses: tuple[str, ...] | None = None) -> list[InterestRow]:
        query = _SELECT
        args: tuple = ()
        if statuses:
            query += f" WHERE i.status IN ({','.join('?' * len(statuses))})"
            args = statuses
        query += " ORDER BY i.id"
        return [_row(r) for r in self._conn.execute(query, args).fetchall()]

    def history(self, interest_id: int) -> list[InterestRow]:
        """The chain of revisions this interest belongs to, oldest first."""
        chain: list[InterestRow] = []
        row = self.get(interest_id)
        # Walk back to the first version, then forward through whatever revised it.
        while row is not None and row.revises_id is not None:
            row = self.get(row.revises_id)
        seen: set[int] = set()
        while row is not None and row.id not in seen:
            chain.append(row)
            seen.add(row.id)
            r = self._conn.execute(
                _SELECT + " WHERE i.revises_id = ? AND i.status != 'rejected' ORDER BY i.id LIMIT 1",
                (row.id,),
            ).fetchone()
            row = _row(r) if r else None
        return chain

    def set_status(self, interest_id: int, status: str) -> bool:
        with self._conn:
            cursor = self._conn.execute(
                "UPDATE interests SET status = ? WHERE id = ?", (status, interest_id)
            )
        return cursor.rowcount == 1

    def approve(self, interest_id: int, now: datetime) -> bool:
        """proposed -> active. A revision supersedes the interest it revises."""
        row = self.get(interest_id)
        if row is None or row.status != "proposed":
            return False
        with self._conn:
            self._conn.execute(
                "UPDATE interests SET status = 'active', offer = NULL, last_seen_at = ? WHERE id = ?",
                (_iso(now), interest_id),
            )
            if row.revises_id is not None:
                self._conn.execute(
                    "UPDATE interests SET status = 'superseded', offer = NULL WHERE id = ?",
                    (row.revises_id,),
                )
        return True

    def reject(self, interest_id: int) -> bool:
        row = self.get(interest_id)
        if row is None or row.status != "proposed":
            return False
        with self._conn:
            self._conn.execute(
                "UPDATE interests SET status = 'rejected', offer = NULL WHERE id = ?", (interest_id,)
            )
        return True

    def mute(self, interest_id: int) -> bool:
        row = self.get(interest_id)
        if row is None or row.status not in ("active", "proposed"):
            return False
        with self._conn:
            self._conn.execute(
                "UPDATE interests SET status = 'muted', offer = NULL, checkin = NULL WHERE id = ?",
                (interest_id,),
            )
        return True

    def defer_offer(self, interest_id: int, now: datetime) -> None:
        with self._conn:
            self._conn.execute(
                "UPDATE interests SET offered_at = ? WHERE id = ? AND offer = 'pending'",
                (_iso(now), interest_id),
            )

    def clear_offer(self, interest_id: int, *, checkin: str | None = None, keep_checkin: bool = False) -> None:
        with self._conn:
            if keep_checkin:
                self._conn.execute("UPDATE interests SET offer = NULL WHERE id = ?", (interest_id,))
            else:
                self._conn.execute(
                    "UPDATE interests SET offer = NULL, checkin = ? WHERE id = ?", (checkin, interest_id)
                )

    def queue_checkin(self, interest_id: int) -> None:
        with self._conn:
            self._conn.execute(
                "UPDATE interests SET checkin = 'queued', offer = 'pending', offered_at = NULL"
                " WHERE id = ? AND checkin IS NULL",
                (interest_id,),
            )

    def touch(self, interest_id: int, now: datetime) -> None:
        """New evidence (or the user's yes): fresh again, and no longer dormant."""
        with self._conn:
            self._conn.execute(
                "UPDATE interests SET last_seen_at = MAX(last_seen_at, ?), checkin = NULL,"
                " offer = CASE WHEN checkin IS NOT NULL THEN NULL ELSE offer END WHERE id = ?",
                (_iso(now), interest_id),
            )

    # -------------------------------------------------------------- evidence

    def add_evidence(self, interest_id: int, episode_id: str, quote: str, ts: datetime) -> bool:
        """Add one supporting utterance. False if it was already recorded."""
        quote = " ".join(quote.split())[:QUOTE_CHARS]
        with self._conn:
            cursor = self._conn.execute(
                "INSERT OR IGNORE INTO evidence (interest_id, episode_id, quote, ts) VALUES (?, ?, ?, ?)",
                (interest_id, episode_id, quote, _iso(ts)),
            )
            if cursor.rowcount == 1:
                self._conn.execute(
                    "UPDATE interests SET last_seen_at = MAX(last_seen_at, ?) WHERE id = ?",
                    (_iso(ts), interest_id),
                )
        return cursor.rowcount == 1

    def evidence(self, interest_id: int) -> list[EvidenceRow]:
        rows = self._conn.execute(
            "SELECT * FROM evidence WHERE interest_id = ? ORDER BY ts", (interest_id,)
        ).fetchall()
        return [
            EvidenceRow(r["interest_id"], r["episode_id"], r["quote"], datetime.fromisoformat(r["ts"]))
            for r in rows
        ]

    # ----------------------------------------------------------------- meta

    def get_meta(self, key: str) -> str | None:
        r = self._conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return r["value"] if r else None

    def set_meta(self, key: str, value: str) -> None:
        with self._conn:
            self._conn.execute(
                "INSERT INTO meta (key, value) VALUES (?, ?)"
                " ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )

    def get_time(self, key: str) -> datetime | None:
        return _parse(self.get_meta(key))

    def set_time(self, key: str, when: datetime) -> None:
        self.set_meta(key, _iso(when))

    # ------------------------------------------------------------------ runs

    def add_run(self, ts: datetime, utterances: int, created: int, outcome: str) -> None:
        with self._conn:
            self._conn.execute(
                "INSERT INTO runs (ts, utterances, created, outcome) VALUES (?, ?, ?, ?)",
                (_iso(ts), utterances, created, outcome),
            )

    def last_runs(self, limit: int = 5) -> list[sqlite3.Row]:
        return self._conn.execute("SELECT * FROM runs ORDER BY id DESC LIMIT ?", (limit,)).fetchall()

    # ---------------------------------------------------------------- delete

    def forget(self, interest_id: int) -> bool:
        with self._conn:
            self._conn.execute("DELETE FROM evidence WHERE interest_id = ?", (interest_id,))
            # Whatever revised or was revised by it loses the link, not its own record.
            self._conn.execute(
                "UPDATE interests SET revises_id = NULL WHERE revises_id = ?", (interest_id,)
            )
            cursor = self._conn.execute("DELETE FROM interests WHERE id = ?", (interest_id,))
        return cursor.rowcount == 1

    def forget_all(self) -> int:
        with self._conn:
            n = self._conn.execute("SELECT COUNT(*) FROM interests").fetchone()[0]
            for table in ("evidence", "interests", "runs", "meta"):
                self._conn.execute(f"DELETE FROM {table}")
        return int(n)

    def close(self) -> None:
        self._conn.close()
