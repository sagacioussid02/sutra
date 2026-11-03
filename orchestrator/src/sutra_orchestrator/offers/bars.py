"""The learned benefit bar: how good an offer must be before Sutra speaks up.

One bar per kind of offer. Outcomes nudge it by small, bounded steps; without new
evidence it drifts back to where it started, so an old bad week does not silence
the feature forever. It starts high on purpose: before Sutra has any evidence,
only clearly useful offers get through.
"""

from __future__ import annotations

from datetime import datetime

from .store import OffersStore

START = {"followup": 0.55, "timely": 0.50}
LOW, HIGH = 0.30, 0.95
STEP = {"accepted": -0.04, "ignored": 0.02, "declined": 0.06, "deferred": 0.0}
DRIFT_PER_DAY = 0.05  # fraction of the distance back to START recovered each day
UNCONNECTED_EXTRA = 0.15  # a signal tied to nothing the user said is held to a higher bar


class Bars:
    def __init__(self, store: OffersStore) -> None:
        self._store = store

    @staticmethod
    def start(kind: str) -> float:
        return START.get(kind, 0.55)

    def value(self, kind: str, now: datetime) -> float:
        stored = self._store.get_bar(kind)
        start = self.start(kind)
        if stored is None:
            return start
        value, at = stored
        days = max((now - at).total_seconds() / 86400.0, 0.0)
        return start + (value - start) * (1.0 - DRIFT_PER_DAY) ** days

    def record(self, kind: str, outcome: str, now: datetime) -> float:
        """Move the bar for one outcome. Returns the new value."""
        value = self.value(kind, now) + STEP.get(outcome, 0.0)
        value = min(HIGH, max(LOW, value))
        self._store.set_bar(kind, value, now)
        return value

    def reset(self) -> None:
        self._store.reset_bars()
