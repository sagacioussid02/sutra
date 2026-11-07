"""The provider: assemble a snapshot from the stores that own the truth, in memory only."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from .snapshot import Field, Snapshot

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Reading:
    """What a source reports: the text, and when it was observed if not just now."""

    text: str
    observed_at: datetime | None = None


Reader = Callable[[], Awaitable["str | Reading | None"]]


@dataclass(frozen=True)
class FieldSpec:
    name: str
    label: str
    source: str  # the store that owns the truth
    read: Reader
    ttl: timedelta | None
    cached: bool = False  # True for sources that cost a tool call; local reads are always fresh


class WorldState:
    def __init__(
        self,
        specs: list[FieldSpec],
        *,
        timeout: float = 2.0,
        budget: int = 700,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._specs = {s.name: s for s in specs}
        self._order = [s.name for s in specs]
        self._timeout = timeout
        self._budget = budget
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._cache: dict[str, Field] = {}
        self._turn: tuple[object, Snapshot] | None = None
        self.enabled = True

    @property
    def names(self) -> list[str]:
        return list(self._order)

    async def snapshot(self, turn: object | None = None) -> Snapshot:
        """Assemble at the first read in a turn and reuse it for the rest of that turn."""
        if turn is not None and self._turn is not None and self._turn[0] is turn:
            return self._turn[1]
        now = self._now()
        results = await asyncio.gather(*(self._observe(n, now, None) for n in self._order))
        fields: dict[str, Field] = {}
        absent: dict[str, str] = {}
        for name, (f, why) in zip(self._order, results):
            if f is not None:
                fields[name] = f
            elif why:
                absent[name] = why
        snap = Snapshot(assembled_at=now, fields=fields, absent=absent)
        if turn is not None:
            self._turn = (turn, snap)
        return snap

    async def field(self, name: str, max_age: timedelta) -> Field | None:
        """One field, guaranteed no older than ``max_age``: only this field is re-read."""
        if name not in self._specs:
            return None
        f, _ = await self._observe(name, self._now(), max_age)
        return f

    async def block(self, turn: object | None = None) -> str:
        if not self.enabled:
            return ""
        snap = await self.snapshot(turn)
        return snap.render(self._now(), self._budget)

    async def _observe(self, name: str, now: datetime, max_age: timedelta | None) -> tuple[Field | None, str]:
        spec = self._specs[name]
        cached = self._cache.get(name)
        if spec.cached and cached is not None:
            limit = max_age if max_age is not None else spec.ttl
            if limit is None or now - cached.observed_at <= limit:
                return cached, ""
        try:
            reading = await asyncio.wait_for(spec.read(), timeout=self._timeout)
        except asyncio.CancelledError:
            raise
        except asyncio.TimeoutError:
            self._cache.pop(name, None)
            return None, "timed out"
        except Exception as exc:  # a failing source is an absent field, never an error or a guess
            log.debug("world-state source %s failed: %s", name, type(exc).__name__)
            self._cache.pop(name, None)
            return None, "unavailable"
        if reading is None:
            self._cache.pop(name, None)
            return None, ""
        text, at = (reading.text, reading.observed_at) if isinstance(reading, Reading) else (reading, None)
        f = Field(name, spec.label, " ".join(text.split()), spec.source, at or now, spec.ttl)
        if spec.cached:
            self._cache[name] = f
        return f, ""
