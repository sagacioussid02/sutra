"""SQLite storage for the event log and consumer cursors: private file, versioned schema."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from ..errors import OrchestratorError

SCHEMA_VERSION = 1


class EventsSchemaError(OrchestratorError):
    """The database was written by a newer version of this code."""


_SCHEMA = """
CREATE TABLE events (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    id TEXT NOT NULL UNIQUE,
    source TEXT NOT NULL,
    kind TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    received_at TEXT NOT NULL,
    user_id TEXT NOT NULL,
    payload TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    expires_at TEXT NOT NULL
);
CREATE UNIQUE INDEX events_idem ON events(source, idempotency_key) WHERE idempotency_key != '';

CREATE TABLE cursors (
    consumer TEXT PRIMARY KEY,
    last_seq INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE attempts (
    consumer TEXT NOT NULL,
    seq INTEGER NOT NULL,
    failures INTEGER NOT NULL,
    last_error TEXT NOT NULL,
    PRIMARY KEY (consumer, seq)
);

CREATE TABLE handled (
    consumer TEXT NOT NULL,
    event_id TEXT NOT NULL,
    PRIMARY KEY (consumer, event_id)
);

CREATE TABLE skipped (
    consumer TEXT NOT NULL,
    seq INTEGER NOT NULL,
    error TEXT NOT NULL,
    at TEXT NOT NULL,
    PRIMARY KEY (consumer, seq)
);
"""


def open_events(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    os.close(fd)
    os.chmod(path, 0o600)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        if version > SCHEMA_VERSION:
            raise EventsSchemaError(
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
