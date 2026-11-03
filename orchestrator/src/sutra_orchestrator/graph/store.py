"""The episode graph store: nodes (episodes), typed edges, decay."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .db import open_graph

GRAPH_DB = "graph.db"

MODES = ("explained", "planned", "worked_on", "decided", "asked")
STEPS = ("example", "deeper", "practice", "decision")
EDGE_TYPES = ("same_topic", "extends", "prerequisite_of", "applies_to", "updates")

# Decay: weight halves every HALF_LIFE_DAYS without use. A node below ARCHIVE_BELOW is
# archived (never retrieved); an edge below DROP_EDGE_BELOW is deleted. Code defaults,
# not per-user settings: decay only keeps retrieval clean.
HALF_LIFE_DAYS = 45.0
ARCHIVE_BELOW = 0.12
DROP_EDGE_BELOW = 0.05
TOUCH_BOOST = 0.3
MAX_NODES = 500  # a rail on the size of the file, not a tuning knob


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def decayed(weight: float, since: datetime, now: datetime) -> float:
    days = max((now - since).total_seconds() / 86400.0, 0.0)
    return weight * 0.5 ** (days / HALF_LIFE_DAYS)


@dataclass(frozen=True)
class Node:
    id: int
    topic: str
    gist: str
    mode: str
    open: tuple[str, ...]
    entities: tuple[str, ...]
    weight: float
    status: str
    created_at: datetime
    last_touched: datetime

    def live_weight(self, now: datetime) -> float:
        return decayed(self.weight, self.last_touched, now)


@dataclass(frozen=True)
class Edge:
    id: int
    a: int
    b: int
    type: str
    strength: float
    reason: str
    weight: float
    touched: datetime

    def other(self, node_id: int) -> int:
        return self.b if self.a == node_id else self.a


def _node(r: sqlite3.Row) -> Node:
    return Node(
        id=r["id"],
        topic=r["topic"],
        gist=r["gist"],
        mode=r["mode"],
        open=tuple(json.loads(r["open"])),
        entities=tuple(json.loads(r["entities"])),
        weight=r["weight"],
        status=r["status"],
        created_at=datetime.fromisoformat(r["created_at"]),
        last_touched=datetime.fromisoformat(r["last_touched"]),
    )


def _edge(r: sqlite3.Row) -> Edge:
    return Edge(
        id=r["id"],
        a=r["a"],
        b=r["b"],
        type=r["type"],
        strength=r["strength"],
        reason=r["reason"],
        weight=r["weight"],
        touched=datetime.fromisoformat(r["touched"]),
    )


class GraphStore:
    def __init__(self, directory: str | Path) -> None:
        self._conn = open_graph(Path(directory) / GRAPH_DB)

    def close(self) -> None:
        self._conn.close()

    # ----------------------------------------------------------------- nodes

    def add_node(
        self,
        topic: str,
        gist: str,
        mode: str,
        open_items: list[str],
        entities: list[str],
        now: datetime,
    ) -> int:
        with self._conn:
            cur = self._conn.execute(
                "INSERT INTO nodes (topic, gist, mode, open, entities, weight, status, created_at, last_touched)"
                " VALUES (?, ?, ?, ?, ?, 1.0, 'active', ?, ?)",
                (topic, gist, mode, json.dumps(open_items), json.dumps(entities), _iso(now), _iso(now)),
            )
        return int(cur.lastrowid)

    def get(self, node_id: int) -> Node | None:
        row = self._conn.execute("SELECT * FROM nodes WHERE id = ?", (node_id,)).fetchone()
        return _node(row) if row else None

    def list(self, *, include_archived: bool = False) -> list[Node]:
        sql = "SELECT * FROM nodes" + ("" if include_archived else " WHERE status = 'active'")
        return [_node(r) for r in self._conn.execute(sql + " ORDER BY last_touched DESC")]

    def count(self) -> int:
        return self._conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]

    def merge_into(
        self,
        node_id: int,
        gist: str,
        open_items: list[str],
        entities: list[str],
        now: datetime,
    ) -> None:
        """Fold a repeated episode into an existing node: newest gist and open items win."""
        node = self.get(node_id)
        if node is None:
            return
        merged = list(dict.fromkeys([*node.entities, *entities]))[:8]
        weight = min(1.0, node.live_weight(now) + TOUCH_BOOST)
        with self._conn:
            self._conn.execute(
                "UPDATE nodes SET gist = ?, open = ?, entities = ?, weight = ?, status = 'active',"
                " last_touched = ? WHERE id = ?",
                (gist, json.dumps(open_items), json.dumps(merged), weight, _iso(now), node_id),
            )

    def touch(self, node_id: int, now: datetime) -> None:
        node = self.get(node_id)
        if node is None:
            return
        weight = min(1.0, node.live_weight(now) + TOUCH_BOOST)
        with self._conn:
            self._conn.execute(
                "UPDATE nodes SET weight = ?, last_touched = ?, status = 'active' WHERE id = ?",
                (weight, _iso(now), node_id),
            )

    def set_open(self, node_id: int, open_items: list[str]) -> None:
        with self._conn:
            self._conn.execute(
                "UPDATE nodes SET open = ? WHERE id = ?", (json.dumps(open_items), node_id)
            )

    # ----------------------------------------------------------------- edges

    def add_edge(
        self, a: int, b: int, type_: str, strength: float, reason: str, now: datetime
    ) -> None:
        with self._conn:
            self._conn.execute(
                "INSERT INTO edges (a, b, type, strength, reason, weight, touched)"
                " VALUES (?, ?, ?, ?, ?, 1.0, ?)"
                " ON CONFLICT(a, b, type) DO UPDATE SET strength = MAX(strength, excluded.strength),"
                " reason = excluded.reason, weight = 1.0, touched = excluded.touched",
                (a, b, type_, strength, reason, _iso(now)),
            )

    def edges_of(self, node_id: int) -> list[Edge]:
        rows = self._conn.execute(
            "SELECT * FROM edges WHERE a = ? OR b = ? ORDER BY strength DESC", (node_id, node_id)
        )
        return [_edge(r) for r in rows]

    def edge_count(self) -> int:
        return self._conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]

    def reattach_edges(self, old: int, new: int) -> None:
        """Point a discarded node's edges at the node it was merged into."""
        with self._conn:
            for e in self.edges_of(old):
                a, b = (new if e.a == old else e.a), (new if e.b == old else e.b)
                if a != b:
                    self._conn.execute(
                        "INSERT OR IGNORE INTO edges (a, b, type, strength, reason, weight, touched)"
                        " VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (a, b, e.type, e.strength, e.reason, e.weight, _iso(e.touched)),
                    )
            self._conn.execute("DELETE FROM edges WHERE a = ? OR b = ?", (old, old))

    # ----------------------------------------------------------------- decay

    def decay(self, now: datetime) -> tuple[int, int]:
        """Archive faded nodes, drop faded edges, enforce the size rail. Returns (archived, deleted)."""
        archived = deleted = 0
        with self._conn:
            for node in self.list():
                if node.live_weight(now) < ARCHIVE_BELOW:
                    self._conn.execute("UPDATE nodes SET status = 'archived' WHERE id = ?", (node.id,))
                    archived += 1
            for r in self._conn.execute("SELECT * FROM edges").fetchall():
                edge = _edge(r)
                if decayed(edge.weight, edge.touched, now) < DROP_EDGE_BELOW:
                    self._conn.execute("DELETE FROM edges WHERE id = ?", (edge.id,))
            excess = self.count() - MAX_NODES
            if excess > 0:
                # Weakest archived first, then weakest of all.
                ranked = sorted(
                    self.list(include_archived=True),
                    key=lambda n: (n.status != "archived", n.live_weight(now)),
                )
                for node in ranked[:excess]:
                    self._delete(node.id)
                    deleted += 1
        return archived, deleted

    def _delete(self, node_id: int) -> None:
        self._conn.execute("DELETE FROM edges WHERE a = ? OR b = ?", (node_id, node_id))
        self._conn.execute("DELETE FROM nodes WHERE id = ?", (node_id,))

    # ---------------------------------------------------------------- forget

    def forget(self, node_id: int) -> bool:
        with self._conn:
            exists = self._conn.execute("SELECT 1 FROM nodes WHERE id = ?", (node_id,)).fetchone()
            if exists:
                self._delete(node_id)
        return bool(exists)

    def forget_all(self) -> int:
        with self._conn:
            n = self.count()
            self._conn.execute("DELETE FROM edges")
            self._conn.execute("DELETE FROM nodes")
        return n
