"""Deterministic reminder parsing: no model, no guessing.

The parser is a fixed set of patterns evaluated in code. If none of them
match, it returns ``None`` and the caller asks the user to rephrase — a
reminder set for the wrong time is worse than no reminder.

Supported forms (the text after "remind me", or a ``/remind`` argument):

- ``in 20 minutes <text>``, ``in 2 hours <text>``, ``in an hour <text>``,
  ``in half an hour <text>``
- ``at 5pm <text>``, ``at 5:30pm <text>``, ``at 17:30 <text>``,
  ``at noon <text>``, ``at midnight <text>`` — today, or tomorrow if that
  time has already passed today
- ``today at 5pm <text>`` — today even if the time has passed is *not*
  allowed; a past time today returns ``None`` rather than silently
  becoming tomorrow, because the user said "today"
- ``tomorrow at 9am <text>``

A leading "to" before the reminder text is optional and is stripped.
A request with a time but no text is unparseable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class ParsedReminder:
    fire_at: datetime  # aware, in tz
    text: str


_REMIND_ME = re.compile(r"^\s*remind\s+me\b", re.IGNORECASE)

_TOD = r"(?:noon|midnight|\d{1,2}(?::\d{2})?\s*(?:am|pm)|\d{1,2}:\d{2})"

_RELATIVE = re.compile(
    r"^in\s+(?P<amount>\d+|a|an)\s*(?P<unit>minutes?|mins?|hours?|hrs?)\b",
    re.IGNORECASE,
)
_HALF_HOUR = re.compile(r"^in\s+half\s+an?\s+hour\b", re.IGNORECASE)
_TOMORROW_AT = re.compile(rf"^tomorrow\s+at\s+(?P<tod>{_TOD})\b", re.IGNORECASE)
_TODAY_AT = re.compile(rf"^today\s+at\s+(?P<tod>{_TOD})\b", re.IGNORECASE)
_AT = re.compile(rf"^at\s+(?P<tod>{_TOD})\b", re.IGNORECASE)


def reminder_request(utterance: str) -> str | None:
    """Return what follows "remind me" in an utterance, or None if the
    utterance is not a reminder request."""
    match = _REMIND_ME.match(utterance)
    if match is None:
        return None
    return utterance[match.end() :].strip()


def _time_of_day(spec: str) -> time | None:
    spec = spec.strip().lower()
    if spec == "noon":
        return time(12, 0)
    if spec == "midnight":
        return time(0, 0)
    match = re.fullmatch(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)", spec)
    if match:
        hour, minute = int(match.group(1)), int(match.group(2) or 0)
        if not 1 <= hour <= 12 or minute > 59:
            return None
        if match.group(3) == "am":
            hour = 0 if hour == 12 else hour
        else:
            hour = 12 if hour == 12 else hour + 12
        return time(hour, minute)
    match = re.fullmatch(r"(\d{1,2}):(\d{2})", spec)
    if match:
        hour, minute = int(match.group(1)), int(match.group(2))
        if hour > 23 or minute > 59:
            return None
        return time(hour, minute)
    return None


def _rest(text: str) -> str:
    """The reminder text after a time spec: trimmed, leading "to" removed."""
    text = text.strip()
    if text.lower().startswith("to "):
        text = text[3:].strip()
    return text


def _at_on(day_offset: int, tod: time, now: datetime, tz: ZoneInfo) -> datetime:
    day = now.astimezone(tz).date() + timedelta(days=day_offset)
    return datetime.combine(day, tod, tzinfo=tz)


def parse_request(request: str, now: datetime, tz: ZoneInfo) -> ParsedReminder | None:
    """Parse a reminder request (the words after "remind me").

    ``now`` is an aware datetime; wall-clock forms are read in ``tz``.
    Returns None when no supported pattern matches — never a guess.
    """
    text = request.strip()
    if not text:
        return None
    local_now = now.astimezone(tz)

    match = _HALF_HOUR.match(text)
    if match:
        rest = _rest(text[match.end() :])
        if rest:
            # Relative times are elapsed time: add in UTC so a reminder
            # "in 24 hours" is 24 hours later even across a DST change,
            # not 24 wall-clock hours.
            fire_at = (local_now.astimezone(timezone.utc) + timedelta(minutes=30)).astimezone(tz)
            return ParsedReminder(fire_at, rest)
        return None

    match = _RELATIVE.match(text)
    if match:
        amount_raw = match.group("amount").lower()
        amount = 1 if amount_raw in ("a", "an") else int(amount_raw)
        if amount < 1:
            return None
        unit = match.group("unit").lower()
        delta = (
            timedelta(hours=amount) if unit.startswith("h") else timedelta(minutes=amount)
        )
        rest = _rest(text[match.end() :])
        if rest:
            fire_at = (local_now.astimezone(timezone.utc) + delta).astimezone(tz)
            return ParsedReminder(fire_at, rest)
        return None

    for pattern, mode in ((_TOMORROW_AT, "tomorrow"), (_TODAY_AT, "today"), (_AT, "at")):
        match = pattern.match(text)
        if match is None:
            continue
        tod = _time_of_day(match.group("tod"))
        if tod is None:
            return None
        rest = _rest(text[match.end() :])
        if not rest:
            return None
        if mode == "tomorrow":
            fire_at = _at_on(1, tod, now, tz)
        elif mode == "today":
            fire_at = _at_on(0, tod, now, tz)
            if fire_at <= local_now:
                return None  # "today at" a past time: ask, don't roll over
        else:
            fire_at = _at_on(0, tod, now, tz)
            if fire_at <= local_now:
                fire_at = _at_on(1, tod, now, tz)
        return ParsedReminder(fire_at, rest)

    return None
