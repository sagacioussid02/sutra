"""SQLite storage for people and plans: private file, versioned schema."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from ..errors import OrchestratorError

SCHEMA_VERSION = 1


class LifeSchemaError(OrchestratorError):
    """The database was written by a newer version of this code."""


_SCHEMA = """
CREATE TABLE people (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    relation TEXT NOT NULL DEFAULT '',
    first_seen TEXT NOT NULL,
    last_mentioned TEXT NOT NULL,
    mentions INTEGER NOT NULL DEFAULT 1
);
CREATE UNIQUE INDEX people_name ON people(name COLLATE NOCASE);

CREATE TABLE plans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    text TEXT NOT NULL,
    who TEXT NOT NULL DEFAULT '',
    when_date TEXT,
    status TEXT NOT NULL CHECK (status IN ('upcoming', 'asked', 'done', 'dropped')),
    created_at TEXT NOT NULL,
    asked_at TEXT,
    retry_after TEXT
);
CREATE INDEX plans_status ON plans(status);

CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""


def open_life(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    os.close(fd)
    os.chmod(path, 0o600)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        if version > SCHEMA_VERSION:
            raise LifeSchemaError(
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
