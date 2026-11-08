"""SQLite storage for patch runs: private file, versioned schema (same rules as ``agents/db.py``)."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from ..errors import OrchestratorError

SCHEMA_VERSION = 1


class PatchSchemaError(OrchestratorError):
    """The database was written by a newer version of this code."""


_SCHEMA = """
CREATE TABLE patches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN
        ('running', 'drafted', 'partial', 'rejected', 'failed', 'interrupted', 'discarded')),
    created_at TEXT NOT NULL,
    finished_at TEXT,
    branch TEXT NOT NULL DEFAULT '',
    tool_calls INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    reason TEXT NOT NULL DEFAULT '',
    summary TEXT NOT NULL DEFAULT '',
    files TEXT NOT NULL DEFAULT '[]',
    refusals INTEGER NOT NULL DEFAULT 0,
    test_status TEXT NOT NULL DEFAULT 'untested',
    test_detail TEXT NOT NULL DEFAULT '',
    diff_stat TEXT NOT NULL DEFAULT ''
);
CREATE INDEX patches_created ON patches(created_at);
"""


def open_patches(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    os.close(fd)
    os.chmod(path, 0o600)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        if version > SCHEMA_VERSION:
            raise PatchSchemaError(
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
