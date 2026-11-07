"""SQLite storage: private files, schema, and version checking."""

from __future__ import annotations

import os
import shutil
import sqlite3
from pathlib import Path

from ..errors import OrchestratorError

SCHEMA_VERSION = 2


class MemorySchemaError(OrchestratorError):
    """The database was written by a newer version of this code."""


_V2_TABLES = """
-- Every episode that supports a distilled memory (plural provenance).
CREATE TABLE memory_episodes (
    memory_id INTEGER NOT NULL,
    episode_id TEXT NOT NULL,
    PRIMARY KEY (memory_id, episode_id)
);
CREATE INDEX memory_episodes_memory ON memory_episodes(memory_id);

-- Distillation bookkeeping: the watermark and the last pass.
CREATE TABLE distill_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""

_V1_TO_V2 = """
BEGIN;
ALTER TABLE memories RENAME TO memories_v1;
CREATE TABLE memories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL CHECK (kind IN ('fact', 'preference', 'routine', 'correction', 'commitment')),
    source TEXT NOT NULL CHECK (source IN ('user_stated', 'inferred', 'tool_derived')),
    status TEXT NOT NULL CHECK (status IN ('active', 'proposed', 'rejected', 'superseded')),
    content TEXT NOT NULL,
    spoken TEXT,
    episode_id TEXT,
    tool_context INTEGER NOT NULL DEFAULT 0,
    approved_by_user INTEGER NOT NULL DEFAULT 0,
    superseded_by INTEGER,
    created_at TEXT NOT NULL,
    last_used_at TEXT,
    distilled INTEGER NOT NULL DEFAULT 0,
    horizon TEXT,
    replaces INTEGER,
    support INTEGER NOT NULL DEFAULT 1
);
INSERT INTO memories (id, kind, source, status, content, spoken, episode_id, tool_context,
    approved_by_user, superseded_by, created_at, last_used_at)
SELECT id, kind, source, status, content, spoken, episode_id, tool_context,
    approved_by_user, superseded_by, created_at, last_used_at FROM memories_v1;
DROP TABLE memories_v1;
CREATE INDEX memories_status ON memories(status);
""" + _V2_TABLES + """
PRAGMA user_version = 2;
COMMIT;
"""

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
    kind TEXT NOT NULL CHECK (kind IN ('fact', 'preference', 'routine', 'correction', 'commitment')),
    source TEXT NOT NULL CHECK (source IN ('user_stated', 'inferred', 'tool_derived')),
    status TEXT NOT NULL CHECK (status IN ('active', 'proposed', 'rejected', 'superseded')),
    content TEXT NOT NULL,
    spoken TEXT,
    episode_id TEXT,
    tool_context INTEGER NOT NULL DEFAULT 0,
    approved_by_user INTEGER NOT NULL DEFAULT 0,
    superseded_by INTEGER,
    created_at TEXT NOT NULL,
    last_used_at TEXT,
    distilled INTEGER NOT NULL DEFAULT 0,
    horizon TEXT,
    replaces INTEGER,
    support INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX memories_status ON memories(status);

-- rowid of this table is memories.id; maintained by the provider.
CREATE VIRTUAL TABLE memories_fts USING fts5(content, tokenize = 'porter unicode61');
""" + _V2_TABLES

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


def _backup_v1(path: Path) -> None:
    """Keep a private copy of a version-1 memory database before it is migrated."""
    backup = path.with_name(path.name + ".v1.bak")
    if not backup.exists():
        shutil.copy2(path, backup)
        os.chmod(backup, 0o600)


def _open(path: Path, schema: str, migrate: str | None = None) -> sqlite3.Connection:
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
        elif version == 1 and migrate is not None:
            conn.commit()
            _backup_v1(path)
            conn.executescript(migrate)
    except BaseException:
        conn.close()
        raise
    return conn


def open_main(path: Path) -> sqlite3.Connection:
    return _open(path, _MAIN_SCHEMA, _V1_TO_V2)


def open_archive(path: Path) -> sqlite3.Connection:
    return _open(path, _ARCHIVE_SCHEMA)
