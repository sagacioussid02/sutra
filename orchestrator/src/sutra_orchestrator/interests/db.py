"""SQLite storage for the interest profile: private file, versioned schema.

Mirrors ``reminders/db.py`` and ``agents/db.py``: owner-only permissions, and a
database written by a newer version of this code is refused without being modified.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from ..errors import OrchestratorError

SCHEMA_VERSION = 1


class InterestSchemaError(OrchestratorError):
    """The database was written by a newer version of this code."""


_SCHEMA = """
CREATE TABLE interests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    topic TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('proposed', 'active', 'rejected', 'muted', 'superseded')),
    source TEXT NOT NULL CHECK (source IN ('reflection', 'user')),
    created_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    revises_id INTEGER,
    change_before TEXT,
    change_now TEXT,
    offer TEXT CHECK (offer IN ('pending')),
    offered_at TEXT,
    checkin TEXT CHECK (checkin IN ('queued', 'asked'))
);
CREATE INDEX interests_status ON interests(status);

CREATE TABLE evidence (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    interest_id INTEGER NOT NULL,
    episode_id TEXT NOT NULL,
    quote TEXT NOT NULL,
    ts TEXT NOT NULL,
    UNIQUE (interest_id, episode_id)
);

CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);

CREATE TABLE runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    utterances INTEGER NOT NULL,
    created INTEGER NOT NULL,
    outcome TEXT NOT NULL
);
"""


def open_interests(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    os.close(fd)
    os.chmod(path, 0o600)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        if version > SCHEMA_VERSION:
            raise InterestSchemaError(
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
