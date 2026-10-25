"""SQLite storage: private files, schema, and version checking."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from ..errors import OrchestratorError

SCHEMA_VERSION = 1


class MemorySchemaError(OrchestratorError):
    """The database was written by a newer version of this code."""


_MAIN_SCHEMA = """
CREATE TABLE episodes (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    ts TEXT NOT NULL,
    utterance TEXT NOT NULL,
    reply TEXT,
    tools TEXT NOT NULL DEFAULT '[]',
    confirmation TEXT
);
CREATE INDEX episodes_ts ON episodes(ts);

CREATE TABLE memories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL CHECK (kind IN ('fact', 'preference', 'routine', 'correction')),
    source TEXT NOT NULL CHECK (source IN ('user_stated', 'inferred', 'tool_derived')),
    status TEXT NOT NULL CHECK (status IN ('active', 'proposed', 'rejected', 'superseded')),
    content TEXT NOT NULL,
    spoken TEXT,
    episode_id TEXT,
    tool_context INTEGER NOT NULL DEFAULT 0,
    approved_by_user INTEGER NOT NULL DEFAULT 0,
    superseded_by INTEGER,
    created_at TEXT NOT NULL,
    last_used_at TEXT
);
CREATE INDEX memories_status ON memories(status);

-- rowid of this table is memories.id; maintained by the provider.
CREATE VIRTUAL TABLE memories_fts USING fts5(content, tokenize = 'porter unicode61');
"""

_ARCHIVE_SCHEMA = """
CREATE TABLE episodes (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    ts TEXT NOT NULL,
    utterance TEXT NOT NULL,
    reply TEXT,
    tools TEXT NOT NULL DEFAULT '[]',
    confirmation TEXT
);
CREATE INDEX episodes_ts ON episodes(ts);
"""


def _connect_private(path: Path) -> sqlite3.Connection:
    """Open ``path`` as a database only the owner can read or write."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
        os.close(fd)
    os.chmod(path, 0o600)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def _open(path: Path, schema: str) -> sqlite3.Connection:
    conn = _connect_private(path)
    try:
        # Read the version before touching anything, so a newer database is
        # refused without being modified.
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        if version > SCHEMA_VERSION:
            raise MemorySchemaError(
                f"{path} has schema version {version}, but this code understands up to "
                f"{SCHEMA_VERSION}. Update the orchestrator; the file was not modified."
            )
        if version == 0:
            with conn:
                conn.executescript(schema)
                conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    except BaseException:
        conn.close()
        raise
    return conn


def open_main(path: Path) -> sqlite3.Connection:
    return _open(path, _MAIN_SCHEMA)


def open_archive(path: Path) -> sqlite3.Connection:
    return _open(path, _ARCHIVE_SCHEMA)
