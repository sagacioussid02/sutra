"""One arbiter in front of everything proactive.

It decides only whether something may be said right now. What is worth saying is
the judge's business. The fixed rails live here and nowhere else: a daily maximum
across all kinds (urgent offers may exceed it), no offer during a confirmation or
while another is open, and the user's own stops, which are final.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from ..interests.reflect import similar
from .store import OffersStore

DEFAULT_DAILY_MAX = 4
ORDER = {"urgent": 0, "followup": 1, "timely": 1, "nudge": 2}  # lower goes first


@dataclass(frozen=True)
class Permit:
    ok: bool
    reason: str = ""


class Arbiter:
    def __init__(self, store: OffersStore, tz: ZoneInfo, *, daily_max: int = DEFAULT_DAILY_MAX) -> None:
        self._store = store
        self._tz = tz
        self._daily_max = daily_max

    def enabled(self) -> bool:
        return self._store.get_meta("enabled") != "0"

    def is_blocked(self, kind: str, topic: str) -> bool:
        for b in self._store.blocks():
            if b.kind not in ("", kind):
                continue
            if not b.topic:
                return True
            if topic and (similar(topic, b.topic) or similar(b.topic, topic)):
                return True
        return False

    def today_count(self, now: datetime) -> int:
        local = now.astimezone(self._tz)
        midnight = local.replace(hour=0, minute=0, second=0, microsecond=0)
        return self._store.made_since(midnight.astimezone(now.tzinfo))

    def permit(
        self,
        kind: str,
        topic: str,
        now: datetime,
        *,
        urgent: bool = False,
        action_pending: bool = False,
        open_offer: bool = False,
    ) -> Permit:
        if not self.enabled():
            return Permit(False, "offers are off")
        if action_pending:
            return Permit(False, "an action is awaiting confirmation")
        if open_offer:
            return Permit(False, "another offer is open")
        if self.is_blocked(kind, topic):
            return Permit(False, "blocked by the user")
        if not urgent and self.today_count(now) >= self._daily_max:
            return Permit(False, "daily maximum reached")
        return Permit(True)
