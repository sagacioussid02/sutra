"""The sandbox profile: throwaway stores, a fake clock, and the guard that refuses anything else.

A battery run touches nothing real. Every store a scenario uses lives under
one sandbox root the harness created for this run, the clock is a value the
battery moves, and mutating gateway tools are recording stubs. The guard
runs before the first turn of a run: if the profile is not the sandbox
profile, or any of its stores could reach a real one, the run aborts and
says why.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

SANDBOX = "sandbox"
SANDBOX_MARKER = ".sutra-dogfood-sandbox"


class ProfileError(RuntimeError):
    """The run's profile is not safe to run a battery against."""


class FakeClock:
    """The only clock a battery run reads. It moves when a step says so."""

    def __init__(self, start: datetime) -> None:
        if start.tzinfo is None:
            raise ValueError("the fake clock needs an aware start time")
        self.t = start

    def __call__(self) -> datetime:
        return self.t

    def advance(self, minutes: float) -> None:
        self.t += timedelta(minutes=minutes)

    def set(self, when: datetime) -> None:
        self.t = when


@dataclass
class Profile:
    """Where a run's stores live, and what kind of profile it is."""

    name: str
    root: Path
    # Directories the live assistant uses. A sandbox store may never sit inside one.
    real_dirs: tuple[Path, ...] = field(default_factory=tuple)

    def store_dir(self, scenario_id: str, store: str) -> Path:
        path = self.root / _safe(scenario_id) / store
        path.mkdir(parents=True, exist_ok=True)
        return path


def _safe(name: str) -> str:
    return "".join(c if c.isalnum() or c in "-_." else "_" for c in name)[:80] or "scenario"


def new_sandbox(real_dirs: tuple[Path, ...] = (), base: Path | None = None) -> Profile:
    """A fresh sandbox profile under a new temporary directory."""
    root = Path(tempfile.mkdtemp(prefix="sutra-dogfood-", dir=base))
    (root / SANDBOX_MARKER).write_text("throwaway stores for one dogfood run\n")
    return Profile(name=SANDBOX, root=root, real_dirs=tuple(Path(d) for d in real_dirs))


def guard(profile: Profile) -> None:
    """Refuse to run unless this is the sandbox profile and nothing in it can reach a real store."""
    if profile.name != SANDBOX:
        raise ProfileError(f"the active profile is {profile.name!r}, not the sandbox profile; no turns were sent")
    root = profile.root.resolve()
    if not (root / SANDBOX_MARKER).is_file():
        raise ProfileError(f"{root} was not created as a sandbox (no marker file); no turns were sent")
    for real in profile.real_dirs:
        real = real.expanduser().resolve()
        if root == real or _inside(root, real) or _inside(real, root):
            raise ProfileError(f"the sandbox root {root} overlaps a real store at {real}; no turns were sent")


def _inside(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent)
    except ValueError:
        return False
    return True


def parse_start(value: str | None) -> datetime:
    """A scenario's start time. Default: a fixed instant, so runs are reproducible."""
    if not value:
        return datetime(2026, 11, 2, 15, 0, tzinfo=timezone.utc)
    when = datetime.fromisoformat(value)
    if when.tzinfo is None:
        raise ValueError(f"start time {value!r} needs a UTC offset")
    return when
