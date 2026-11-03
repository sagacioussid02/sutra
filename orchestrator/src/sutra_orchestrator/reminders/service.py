"""The spoken/typed surface over the store: "remind me ..." handling.

This is the piece the orchestrator calls. It is fully deterministic:
a "remind me" utterance is parsed by :mod:`.parser` before any model
call, the reminder is stored, and the reply confirms the exact fire
time. If the words do not parse, the reply asks for a clearer time
instead of guessing — the model is never asked to interpret the time.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from .parser import parse_request, reminder_request
from .store import ReminderStore

CLARIFY_REPLY = (
    "I couldn't work out when you mean. Try something like "
    "'remind me in 20 minutes to call Sam' or "
    "'remind me tomorrow at 9am to water the plants'."
)


def spoken_when(fire_at: datetime, now: datetime, tz: ZoneInfo) -> str:
    """A short spoken form of a fire time: "today at 5:00 PM"."""
    local = fire_at.astimezone(tz)
    today = now.astimezone(tz).date()
    clock = local.strftime("%I:%M %p").lstrip("0")
    if local.date() == today:
        day = "today"
    elif (local.date() - today).days == 1:
        day = "tomorrow"
    elif (local.date() - today).days < 7:
        day = local.strftime("on %A")
    else:
        day = local.strftime("on %A, %B ") + str(local.day)
    return f"{day} at {clock}"


class ReminderService:
    def __init__(self, store: ReminderStore, tz: ZoneInfo) -> None:
        self._store = store
        self._tz = tz

    @property
    def store(self) -> ReminderStore:
        return self._store

    @property
    def tz(self) -> ZoneInfo:
        return self._tz

    def try_handle(self, utterance: str, now: datetime) -> str | None:
        """Handle a "remind me ..." utterance, returning the reply.

        Returns None when the utterance is not a reminder request, so the
        caller carries on with a normal turn.
        """
        request = reminder_request(utterance)
        if request is None:
            return None
        parsed = parse_request(request, now, self._tz)
        if parsed is None or not parsed.text:
            return CLARIFY_REPLY
        row = self._store.add(parsed.text, parsed.fire_at, str(self._tz), now)
        when = spoken_when(row.fire_at, now, self._tz)
        return f"Okay, I'll remind you: {row.text} — {when}."
