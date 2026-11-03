"""SQLite storage for idle research: private file, versioned schema."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from ..errors import OrchestratorError

SCHEMA_VERSION = 1


class IdleSchemaError(OrchestratorError):
    """The database was written by a newer version of this code."""


_SCHEMA = """
CREATE TABLE runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    topic TEXT NOT NULL,
    brief TEXT NOT NULL,
    kind TEXT NOT NULL,
    outcome TEXT NOT NULL CHECK (outcome IN
        ('running', 'done', 'partial', 'empty', 'failed', 'interrupted', 'skipped')),
    findings TEXT NOT NULL DEFAULT '',
    summary TEXT NOT NULL DEFAULT '',
    signal_id INTEGER,
    created_at TEXT NOT NULL,
    not_before TEXT
);
CREATE INDEX runs_created ON runs(created_at);

CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""


def open_idle(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    os.close(fd)
    os.chmod(path, 0o600)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        if version > SCHEMA_VERSION:
            raise IdleSchemaError(
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
