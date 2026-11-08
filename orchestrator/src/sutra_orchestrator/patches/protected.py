"""The protected-path list: code the drafter can never create, change, rename or delete.

This is a constant, not configuration: nothing at runtime (and no drafter) can edit it. A pattern
ending in ``/`` protects a whole directory; any other pattern is matched against the full path and,
if it has no ``/``, against the file name anywhere in the tree. Matching ignores case, because the
default macOS filesystem does.
"""

from __future__ import annotations

import posixpath
import unicodedata
from fnmatch import fnmatchcase

_PKG = "orchestrator/src/sutra_orchestrator"

PROTECTED: tuple[str, ...] = (
    # The confirmation gate, tool gate and everything that decides what may run.
    f"{_PKG}/safety/",
    f"{_PKG}/auth/",
    f"{_PKG}/classifier.py",
    f"{_PKG}/orchestrator.py",
    f"{_PKG}/gateway.py",
    # This feature itself.
    f"{_PKG}/patches/",
    # The tests that hold those layers to account.
    "orchestrator/tests/test_safety.py",
    "orchestrator/tests/test_auth.py",
    "orchestrator/tests/test_confirmation.py",
    "orchestrator/tests/test_speaker_binding.py",
    "orchestrator/tests/test_patches.py",
    # Gateway authentication, tiers, confirmation, audit and registry.
    "gateway/internal/authcfg/",
    "gateway/internal/confirm/",
    "gateway/internal/audit/",
    "gateway/internal/registry/",
    "gateway/internal/gateway/",
    "gateway/internal/events/",
    "gateway/cmd/",
    # Secrets, tokens and what a draft could use to widen its own reach.
    ".env*",
    "*.pem",
    "*.key",
    "*token*",
    "*.db",
    "gateway/*.yaml",
    ".claude/",
    ".git/",
    ".gitignore",
    ".github/",
    "*.sh",
    "*.pth",
    "conftest.py",
    # Dependencies change by hand.
    "pyproject.toml",
    "go.mod",
    "go.sum",
    "requirements*.txt",
)

# Files whose contents a drafter must not even read.
SECRET: tuple[str, ...] = (".env*", "*.pem", "*.key", "*token*", "*.db")


def normalize(rel: str) -> str | None:
    """A clean repo-relative POSIX path, or None if it is absolute, empty or climbs out."""
    if not isinstance(rel, str) or not rel or "\x00" in rel:
        return None
    rel = unicodedata.normalize("NFC", rel).replace("\\", "/")
    if rel.startswith("/") or (len(rel) > 1 and rel[1] == ":"):
        return None
    clean = posixpath.normpath(rel)
    if clean in (".", "") or clean == ".." or clean.startswith("../"):
        return None
    return clean


def _matches(path: str, patterns: tuple[str, ...]) -> bool:
    low = path.lower()
    parts = low.split("/")
    for pattern in patterns:
        p = pattern.lower()
        if p.endswith("/"):
            name = p.rstrip("/")
            if low == name or low.startswith(p) or ("/" not in name and name in parts[:-1]):
                return True
        elif "/" in p:
            if fnmatchcase(low, p):
                return True
        elif any(fnmatchcase(part, p) for part in parts):
            return True
    return False


def is_protected(rel: str) -> bool:
    """True when ``rel`` is on the list, or is not a path we can reason about (fail closed)."""
    clean = normalize(rel)
    return clean is None or _matches(clean, PROTECTED)


def is_secret(rel: str) -> bool:
    clean = normalize(rel)
    return clean is None or _matches(clean, SECRET)
