"""SQLite storage for reminders: private files, schema, and version checking.

Deliberately mirrors ``memstore/db.py``: the reminders database is a
separate file from the memory database, opened with owner-only
permissions, and a database written by a newer version of this code is
refused without being modified.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from ..errors import OrchestratorError

SCHEMA_VERSION = 1


class ReminderSchemaError(OrchestratorError):
    """The database was written by a newer version of this code."""


_SCHEMA = """
CREATE TABLE reminders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    text TEXT NOT NULL,
    fire_at TEXT NOT NULL,
    tz TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('pending', 'fired', 'cancelled')),
    created_at TEXT NOT NULL,
    fired_at TEXT,
    late INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX reminders_due ON reminders(status, fire_at);

CREATE TABLE inbox (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    reminder_id INTEGER NOT NULL REFERENCES reminders(id),
    text TEXT NOT NULL,
    fire_at TEXT NOT NULL,
    delivered_at TEXT NOT NULL,
    late INTEGER NOT NULL DEFAULT 0,
    seen INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX inbox_unseen ON inbox(seen);
"""


def open_reminders(path: Path) -> sqlite3.Connection:
    """Open ``path`` as a reminders database only the owner can read or write."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
        os.close(fd)
    os.chmod(path, 0o600)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        # Read the version before touching anything, so a newer database is
        # refused without being modified.
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        if version > SCHEMA_VERSION:
            raise ReminderSchemaError(
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
