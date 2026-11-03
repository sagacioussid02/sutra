"""The offers store: what was offered, how the user reacted, what was learned."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .db import open_offers

OFFERS_DB = "offers.db"
RESOLVED = ("accepted", "deferred", "declined", "ignored")


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def _parse(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


@dataclass(frozen=True)
class OfferRow:
    id: int
    kind: str
    style: str
    topic: str
    node_id: int | None
    signal_id: int | None
    step: str
    benefit: float
    bar: float
    teaser: str
    reason: str
    retry_hours: float
    urgent: bool
    outcome: str
    created_at: datetime
    local_hour: int


@dataclass(frozen=True)
class Signal:
    id: int
    kind: str
    summary: str
    source: str
    urgency: str
    safety: bool
    expires_at: datetime
    topic_hint: str
    created_at: datetime
    status: str
    hold_until: datetime | None
    style: str | None
    teaser: str | None
    benefit: float | None
    reason: str | None
    retry_hours: float | None
    urgent_path: bool

    @property
    def topic(self) -> str:
        return self.topic_hint or self.kind


@dataclass(frozen=True)
class Block:
    id: int
    kind: str  # "followup", "timely", "nudge" or "" for any kind
    topic: str  # "" for the whole kind
    created_at: datetime


def _offer(r: sqlite3.Row) -> OfferRow:
    return OfferRow(
        id=r["id"], kind=r["kind"], style=r["style"], topic=r["topic"], node_id=r["node_id"],
        signal_id=r["signal_id"], step=r["step"], benefit=r["benefit"], bar=r["bar"],
        teaser=r["teaser"], reason=r["reason"], retry_hours=r["retry_hours"],
        urgent=bool(r["urgent"]), outcome=r["outcome"],
        created_at=datetime.fromisoformat(r["created_at"]), local_hour=r["local_hour"],
    )


def _signal(r: sqlite3.Row) -> Signal:
    return Signal(
        id=r["id"], kind=r["kind"], summary=r["summary"], source=r["source"],
        urgency=r["urgency"], safety=bool(r["safety"]),
        expires_at=datetime.fromisoformat(r["expires_at"]), topic_hint=r["topic_hint"],
        created_at=datetime.fromisoformat(r["created_at"]), status=r["status"],
        hold_until=_parse(r["hold_until"]), style=r["style"], teaser=r["teaser"],
        benefit=r["benefit"], reason=r["reason"], retry_hours=r["retry_hours"],
        urgent_path=bool(r["urgent_path"]),
    )


class OffersStore:
    def __init__(self, directory: str | Path) -> None:
        self._conn = open_offers(Path(directory) / OFFERS_DB)

    def close(self) -> None:
        self._conn.close()

    # ---------------------------------------------------------------- offers

    def add_offer(
        self,
        *,
        kind: str,
        style: str,
        topic: str,
        step: str,
        benefit: float,
        bar: float,
        teaser: str,
        reason: str,
        retry_hours: float,
        now: datetime,
        local_hour: int,
        outcome: str = "open",
        node_id: int | None = None,
        signal_id: int | None = None,
        urgent: bool = False,
    ) -> int:
        with self._conn:
            cur = self._conn.execute(
                "INSERT INTO offers (kind, style, topic, node_id, signal_id, step, benefit, bar, teaser,"
                " reason, retry_hours, urgent, outcome, created_at, local_hour)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (kind, style, topic, node_id, signal_id, step, benefit, bar, teaser, reason,
                 retry_hours, int(urgent), outcome, _iso(now), local_hour),
            )
        return int(cur.lastrowid)

    def get_offer(self, offer_id: int) -> OfferRow | None:
        row = self._conn.execute("SELECT * FROM offers WHERE id = ?", (offer_id,)).fetchone()
        return _offer(row) if row else None

    def resolve(self, offer_id: int, outcome: str, now: datetime) -> None:
        with self._conn:
            self._conn.execute(
                "UPDATE offers SET outcome = ?, resolved_at = ? WHERE id = ?",
                (outcome, _iso(now), offer_id),
            )

    def recent(self, limit: int = 20) -> list[OfferRow]:
        rows = self._conn.execute("SELECT * FROM offers ORDER BY id DESC LIMIT ?", (limit,))
        return [_offer(r) for r in rows]

    def made_since(self, since: datetime) -> int:
        """Offers actually put to the user since a time (not those the judge only held)."""
        return self._conn.execute(
            "SELECT COUNT(*) FROM offers WHERE created_at >= ? AND outcome != 'held'", (_iso(since),)
        ).fetchone()[0]

    def last_made(self) -> datetime | None:
        row = self._conn.execute(
            "SELECT created_at FROM offers WHERE outcome != 'held' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return _parse(row["created_at"]) if row else None

    def outcome_counts(self, kind: str, since: datetime) -> dict[str, int]:
        rows = self._conn.execute(
            "SELECT outcome, COUNT(*) AS n FROM offers WHERE kind = ? AND created_at >= ?"
            " AND outcome IN ('accepted', 'deferred', 'declined', 'ignored')"
            " AND (signal_id IS NULL OR signal_id NOT IN (SELECT id FROM signals WHERE source = 'self-learning'))"
            " GROUP BY outcome",
            (kind, _iso(since)),
        )
        return {r["outcome"]: r["n"] for r in rows}

    def kind_topic_outcomes(self, since: datetime) -> list[tuple[str, str, str]]:
        rows = self._conn.execute(
            "SELECT kind, topic, outcome FROM offers WHERE created_at >= ?"
            " AND outcome IN ('accepted', 'deferred', 'declined', 'ignored')"
            " AND (signal_id IS NULL OR signal_id NOT IN (SELECT id FROM signals WHERE source = 'self-learning'))",
            (_iso(since),),
        )
        return [(r["kind"], r["topic"], r["outcome"]) for r in rows]

    def topic_outcomes(self, since: datetime) -> list[tuple[str, str]]:
        rows = self._conn.execute(
            "SELECT topic, outcome FROM offers WHERE created_at >= ?"
            " AND outcome IN ('accepted', 'deferred', 'declined', 'ignored')"
            " AND (signal_id IS NULL OR signal_id NOT IN (SELECT id FROM signals WHERE source = 'self-learning'))",
            (_iso(since),),
        )
        return [(r["topic"], r["outcome"]) for r in rows]

    def node_outcomes(self, node_id: int) -> list[str]:
        rows = self._conn.execute(
            "SELECT outcome FROM offers WHERE node_id = ? AND outcome IN"
            " ('accepted', 'deferred', 'declined', 'ignored') ORDER BY id",
            (node_id,),
        )
        return [r["outcome"] for r in rows]

    def open_offers(self) -> list[OfferRow]:
        rows = self._conn.execute("SELECT * FROM offers WHERE outcome = 'open'")
        return [_offer(r) for r in rows]

    # ------------------------------------------------------------------ bars

    def get_bar(self, kind: str) -> tuple[float, datetime] | None:
        row = self._conn.execute("SELECT value, updated_at FROM bars WHERE kind = ?", (kind,)).fetchone()
        return (row["value"], datetime.fromisoformat(row["updated_at"])) if row else None

    def set_bar(self, kind: str, value: float, now: datetime) -> None:
        with self._conn:
            self._conn.execute(
                "INSERT INTO bars (kind, value, updated_at) VALUES (?, ?, ?)"
                " ON CONFLICT(kind) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at",
                (kind, value, _iso(now)),
            )

    def reset_bars(self) -> None:
        with self._conn:
            self._conn.execute("DELETE FROM bars")

    # ---------------------------------------------------------------- blocks

    def add_block(self, kind: str, topic: str, now: datetime) -> int:
        with self._conn:
            existing = self._conn.execute(
                "SELECT id FROM blocks WHERE kind = ? AND topic = ?", (kind, topic)
            ).fetchone()
            if existing:
                return int(existing["id"])
            cur = self._conn.execute(
                "INSERT INTO blocks (kind, topic, created_at) VALUES (?, ?, ?)", (kind, topic, _iso(now))
            )
        return int(cur.lastrowid)

    def blocks(self) -> list[Block]:
        rows = self._conn.execute("SELECT * FROM blocks ORDER BY id")
        return [
            Block(r["id"], r["kind"], r["topic"], datetime.fromisoformat(r["created_at"])) for r in rows
        ]

    def remove_block(self, block_id: int) -> bool:
        with self._conn:
            cur = self._conn.execute("DELETE FROM blocks WHERE id = ?", (block_id,))
        return cur.rowcount > 0

    # ----------------------------------------------------------------- holds

    def set_hold(self, key: str, until: datetime) -> None:
        with self._conn:
            self._conn.execute(
                "INSERT INTO holds (key, until) VALUES (?, ?)"
                " ON CONFLICT(key) DO UPDATE SET until = excluded.until",
                (key, _iso(until)),
            )

    def hold_until(self, key: str) -> datetime | None:
        row = self._conn.execute("SELECT until FROM holds WHERE key = ?", (key,)).fetchone()
        return _parse(row["until"]) if row else None

    # --------------------------------------------------------------- signals

    def add_signal(
        self,
        *,
        kind: str,
        summary: str,
        source: str,
        urgency: str,
        safety: bool,
        expires_at: datetime,
        topic_hint: str,
        urgent_path: bool,
        now: datetime,
    ) -> int:
        with self._conn:
            cur = self._conn.execute(
                "INSERT INTO signals (kind, summary, source, urgency, safety, expires_at, topic_hint,"
                " created_at, status, urgent_path) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'new', ?)",
                (kind, summary, source, urgency, int(safety), _iso(expires_at), topic_hint,
                 _iso(now), int(urgent_path)),
            )
        return int(cur.lastrowid)

    def get_signal(self, signal_id: int) -> Signal | None:
        row = self._conn.execute("SELECT * FROM signals WHERE id = ?", (signal_id,)).fetchone()
        return _signal(row) if row else None

    def signals(self, statuses: tuple[str, ...] | None = None) -> list[Signal]:
        if statuses:
            marks = ",".join("?" * len(statuses))
            rows = self._conn.execute(
                f"SELECT * FROM signals WHERE status IN ({marks}) ORDER BY id", statuses
            )
        else:
            rows = self._conn.execute("SELECT * FROM signals ORDER BY id DESC LIMIT 30")
        return [_signal(r) for r in rows]

    def update_signal(self, signal_id: int, **fields: object) -> None:
        allowed = {"status", "hold_until", "style", "teaser", "benefit", "reason", "retry_hours"}
        sets, values = [], []
        for key, value in fields.items():
            assert key in allowed, key
            sets.append(f"{key} = ?")
            values.append(_iso(value) if isinstance(value, datetime) else value)
        if sets:
            with self._conn:
                self._conn.execute(f"UPDATE signals SET {', '.join(sets)} WHERE id = ?", (*values, signal_id))

    # ------------------------------------------------------------------ meta

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

    def forget_all(self) -> None:
        with self._conn:
            for table in ("offers", "bars", "blocks", "holds", "signals", "meta"):
                self._conn.execute(f"DELETE FROM {table}")
