"""SQLite storage for the episode graph: private file, versioned schema.

Mirrors ``interests/db.py``: owner-only permissions, and a database written by a
newer version of this code is refused without being modified.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from ..errors import OrchestratorError

SCHEMA_VERSION = 1


class GraphSchemaError(OrchestratorError):
    """The database was written by a newer version of this code."""


_SCHEMA = """
CREATE TABLE nodes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    topic TEXT NOT NULL,
    gist TEXT NOT NULL,
    mode TEXT NOT NULL,
    open TEXT NOT NULL,
    entities TEXT NOT NULL,
    weight REAL NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('active', 'archived')),
    created_at TEXT NOT NULL,
    last_touched TEXT NOT NULL
);
CREATE INDEX nodes_status ON nodes(status);

CREATE TABLE edges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    a INTEGER NOT NULL,
    b INTEGER NOT NULL,
    type TEXT NOT NULL,
    strength REAL NOT NULL,
    reason TEXT NOT NULL,
    weight REAL NOT NULL,
    touched TEXT NOT NULL,
    UNIQUE (a, b, type)
);
CREATE INDEX edges_a ON edges(a);
CREATE INDEX edges_b ON edges(b);

CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""


def open_graph(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    os.close(fd)
    os.chmod(path, 0o600)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        if version > SCHEMA_VERSION:
            raise GraphSchemaError(
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
