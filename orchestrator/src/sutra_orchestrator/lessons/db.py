"""SQLite storage for lessons: private file, versioned schema."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from ..errors import OrchestratorError

SCHEMA_VERSION = 1


class LessonSchemaError(OrchestratorError):
    """The database was written by a newer version of this code."""


_SCHEMA = """
CREATE TABLE lessons (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    text TEXT NOT NULL,
    effect TEXT NOT NULL CHECK (effect IN ('guidance', 'block')),
    kind TEXT NOT NULL DEFAULT '',
    topic TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL CHECK (status IN
        ('proposed', 'approved', 'active', 'rejected', 'retired', 'superseded', 'blocked')),
    source TEXT NOT NULL CHECK (source IN ('correction', 'outcomes')),
    revises_id INTEGER,
    reason TEXT NOT NULL DEFAULT '',
    not_working INTEGER NOT NULL DEFAULT 0,
    recurrences INTEGER NOT NULL DEFAULT 0,
    asked_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX lessons_status ON lessons(status);

CREATE TABLE evidence (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lesson_id INTEGER NOT NULL,
    ref TEXT NOT NULL,
    quote TEXT NOT NULL,
    ts TEXT NOT NULL,
    UNIQUE (lesson_id, ref)
);

CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""


def open_lessons(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    os.close(fd)
    os.chmod(path, 0o600)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        if version > SCHEMA_VERSION:
            raise LessonSchemaError(
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
