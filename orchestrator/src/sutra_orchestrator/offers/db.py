"""SQLite storage for offers, outcomes, learned bars, blocks and signals: private file, versioned schema."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from ..errors import OrchestratorError

SCHEMA_VERSION = 1


class OffersSchemaError(OrchestratorError):
    """The database was written by a newer version of this code."""


_SCHEMA = """
CREATE TABLE offers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL CHECK (kind IN ('followup', 'timely', 'nudge')),
    style TEXT NOT NULL CHECK (style IN ('ask', 'tell')),
    topic TEXT NOT NULL,
    node_id INTEGER,
    signal_id INTEGER,
    step TEXT NOT NULL,
    benefit REAL NOT NULL,
    bar REAL NOT NULL,
    teaser TEXT NOT NULL,
    reason TEXT NOT NULL,
    retry_hours REAL NOT NULL,
    urgent INTEGER NOT NULL DEFAULT 0,
    outcome TEXT NOT NULL CHECK (outcome IN
        ('open', 'accepted', 'deferred', 'declined', 'ignored', 'held', 'unresolved')),
    created_at TEXT NOT NULL,
    resolved_at TEXT,
    local_hour INTEGER NOT NULL
);
CREATE INDEX offers_created ON offers(created_at);

CREATE TABLE bars (
    kind TEXT PRIMARY KEY,
    value REAL NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE blocks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,
    topic TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE holds (key TEXT PRIMARY KEY, until TEXT NOT NULL);

CREATE TABLE signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,
    summary TEXT NOT NULL,
    source TEXT NOT NULL,
    urgency TEXT NOT NULL CHECK (urgency IN ('low', 'medium', 'high')),
    safety INTEGER NOT NULL DEFAULT 0,
    expires_at TEXT NOT NULL,
    topic_hint TEXT NOT NULL,
    created_at TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN
        ('new', 'held', 'ready', 'offered', 'done', 'dropped', 'expired')),
    hold_until TEXT,
    style TEXT,
    teaser TEXT,
    benefit REAL,
    reason TEXT,
    retry_hours REAL,
    urgent_path INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX signals_status ON signals(status);

CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""


def open_offers(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    os.close(fd)
    os.chmod(path, 0o600)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        if version > SCHEMA_VERSION:
            raise OffersSchemaError(
                f"{path} has schema version {version}, but this code understands up to "
                f"{SCHEMA_VERSION}. Update the orchestrator; the file was not modified."
            )
        if version == 0:
            with conn:
                conn.executescript(_SCHEMA)
                conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    except BaseException:
        conn.close()
        raise
    return conn
