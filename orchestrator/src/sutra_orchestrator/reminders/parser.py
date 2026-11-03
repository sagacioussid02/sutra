"""Deterministic reminder parsing: no model, no guessing.

The parser is a fixed set of patterns evaluated in code. If the time cannot
be pinned down exactly, it returns ``None`` and the caller asks the user to
rephrase: a reminder set for the wrong time is worse than no reminder.

Supported forms (the time may come before or after the reminder text):

- ``in 20 minutes``, ``in two hours``, ``in an hour``, ``in half an hour``
- ``at 5pm``, ``at 5:30pm``, ``at 17:30``, ``at noon``, ``at midnight``:
  today, or tomorrow if that time has already passed
- ``today / tonight / tomorrow``, a weekday (``on Friday``, ``next Tuesday``)
  or a date (``on November 20th``), with ``at <time>``. A date with no time
  means 9am, and the spoken reply says so.
- ``at 8 tonight``, ``at 3 this afternoon``: a bare hour needs a part of day.
- Leading phrases: ``remind me``, ``can you remind me``, ``set a reminder``.

A time given twice, a bare hour with no am/pm, or no reminder text returns None.
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


_LEAD = re.compile(
    r"^\s*(?:(?:hey|ok|okay)\s+\w+[,\s]+)?"
    r"(?:(?:can|could|would|will)\s+you\s+)?(?:please\s+)?"
    r"(?:remind\s+me|set\s+(?:a|an|me\s+a)\s+reminder)\b[,\s]*",
    re.IGNORECASE,
)
# "remind me what/how..." is a question, not a request to set a reminder.
_QUESTION = re.compile(r"^(?:of|about\s+what|what|how|who|why|when|where|which)\b", re.IGNORECASE)

_NUMBER_WORDS = {
    "a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "fifteen": 15, "twenty": 20,
    "thirty": 30, "forty-five": 45, "sixty": 60,
}
_NUM = r"\d+|" + "|".join(sorted(_NUMBER_WORDS, key=len, reverse=True))
_TOD = r"(?:noon|midnight|\d{1,2}(?::\d{2})?\s*(?:am|pm|a\.m\.|p\.m\.)|\d{1,2}:\d{2})"
_WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
_MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august",
           "september", "october", "november", "december"]

_HALF_HOUR = re.compile(r"\bin\s+half\s+an?\s+hour\b", re.IGNORECASE)
_RELATIVE = re.compile(
    rf"\bin\s+(?P<amount>{_NUM})\s*(?P<unit>minutes?|mins?|hours?|hrs?)\b", re.IGNORECASE
)
_DAY = re.compile(
    r"\b(?:(?P<word>today|tonight|tomorrow)"
    r"|(?:(?:on|next|this)\s+)?(?P<weekday>" + "|".join(_WEEKDAYS) + r")"
    r"|(?:on\s+)?(?P<month>" + "|".join(_MONTHS) + r")\s+(?P<mday>\d{1,2})(?:st|nd|rd|th)?)\b",
    re.IGNORECASE,
)
_DAYPART = re.compile(r"\b(?:this\s+)?(?P<part>morning|afternoon|evening)\b", re.IGNORECASE)
_AT_TOD = re.compile(rf"\b(?:at\s+)?(?P<tod>{_TOD})(?!\w)", re.IGNORECASE)
_AT_BARE = re.compile(r"\bat\s+(?P<hour>\d{1,2})\b(?!:)", re.IGNORECASE)

DEFAULT_HOUR = time(9, 0)  # a date with no time of day: 9am, and the reply says so


def reminder_request(utterance: str) -> str | None:
    """Return what follows "remind me" (or "set a reminder") in an utterance,
    or None if the utterance is not a reminder request."""
    match = _LEAD.match(utterance)
    if match is None:
        return None
    rest = utterance[match.end() :].strip()
    if _QUESTION.match(rest):
        return None
    return rest


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


def _at_on(day_offset: int, tod: time, now: datetime, tz: ZoneInfo) -> datetime:
    day = now.astimezone(tz).date() + timedelta(days=day_offset)
    return datetime.combine(day, tod, tzinfo=tz)


def _clean(text: str) -> str:
    """Reminder text left after the time words are cut out."""
    text = re.sub(r"\s+", " ", text).strip(" ,.;")
    text = re.sub(r"^(?:(?:to|for|that)\s+)+", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+(?:on|at|in|by|for)$", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^(?:on|at|in|by)\s+", "", text, flags=re.IGNORECASE)
    return text.strip(" ,.;")


def _cut(text: str, spans: list[tuple[int, int]]) -> str:
    for a, b in sorted(spans, reverse=True):
        text = text[:a] + " " + text[b:]
    return text


def _inside(inner: tuple[int, int], outer: tuple[int, int]) -> bool:
    return outer[0] <= inner[0] and inner[1] <= outer[1]


def _day_date(match: re.Match[str], local_now: datetime):
    """The calendar date a day expression names, or None if it cannot be placed."""
    today = local_now.date()
    word = (match.group("word") or "").lower()
    if word in ("today", "tonight"):
        return today
    if word == "tomorrow":
        return today + timedelta(days=1)
    if match.group("weekday"):
        target = _WEEKDAYS.index(match.group("weekday").lower())
        ahead = (target - today.weekday()) % 7 or 7
        if (match.group(0) or "").lower().startswith("next"):
            # "next Tuesday" is Tuesday of next week, not the coming one.
            ahead = 7 - today.weekday() + target
        return today + timedelta(days=ahead)
    month = _MONTHS.index(match.group("month").lower()) + 1
    day = int(match.group("mday"))
    for year in (today.year, today.year + 1):
        try:
            candidate = today.replace(year=year, month=month, day=day)
        except ValueError:
            return None
        if candidate >= today:
            return candidate
    return None


def parse_request(request: str, now: datetime, tz: ZoneInfo) -> ParsedReminder | None:
    """Parse a reminder request (the words after "remind me").

    The time may come before or after the reminder text. ``now`` is an
    aware datetime; wall-clock forms are read in ``tz``. Returns None when
    the time cannot be pinned down exactly, or is given twice, so the caller
    asks instead of guessing.
    """
    text = request.strip()
    if not text:
        return None
    local_now = now.astimezone(tz)

    # Elapsed time ("in 20 minutes"): added in UTC so it is exact across DST.
    half = _HALF_HOUR.search(text)
    rel = _RELATIVE.search(text)
    if half or rel:
        if (half and rel) or _DAY.search(text) or _AT_TOD.search(text):
            return None
        if half:
            delta, span = timedelta(minutes=30), half.span()
        else:
            amount_raw = rel.group("amount").lower()
            amount = int(amount_raw) if amount_raw.isdigit() else _NUMBER_WORDS[amount_raw]
            if amount < 1:
                return None
            unit = rel.group("unit").lower()
            delta = timedelta(hours=amount) if unit.startswith("h") else timedelta(minutes=amount)
            span = rel.span()
        rest = _clean(_cut(text, [span]))
        if not rest:
            return None
        return ParsedReminder((local_now.astimezone(timezone.utc) + delta).astimezone(tz), rest)

    spans: list[tuple[int, int]] = []
    days = list(_DAY.finditer(text))
    if len(days) > 1:
        return None
    day = days[0] if days else None
    if day:
        spans.append(day.span())
    parts = list(_DAYPART.finditer(text))
    if len(parts) > 1:
        return None
    part = parts[0].group("part").lower() if parts else None
    if parts:
        spans.append(parts[0].span())
    tods = [m for m in _AT_TOD.finditer(text) if not (day and _inside(m.span(), day.span()))]
    bare = list(_AT_BARE.finditer(text))
    if len(tods) + len(bare) > 1:
        return None
    tonight = bool(day and (day.group("word") or "").lower() == "tonight")
    tod: time | None = None
    if tods:
        tod = _time_of_day(tods[0].group("tod").replace(".", ""))
        if tod is None:
            return None
        spans.append(tods[0].span())
    elif bare:
        # A bare hour ("at 8") is only clear with a part of day ("tonight", "this morning").
        hour = int(bare[0].group("hour"))
        pm = tonight or part in ("afternoon", "evening")
        if not 1 <= hour <= 12 or not (pm or part == "morning"):
            return None
        tod = time(hour % 12 + (12 if pm else 0), 0)
        spans.append(bare[0].span())
    if day is None and tod is None:
        return None
    rest = _clean(_cut(text, spans))
    if not rest:
        return None
    if day is None:
        # Time of day only: today, or tomorrow if it has passed. A named part
        # of day ("this morning") cannot roll over, so a past time is a question.
        fire_at = _at_on(0, tod, now, tz)
        if fire_at <= local_now:
            if part:
                return None
            fire_at = _at_on(1, tod, now, tz)
        return ParsedReminder(fire_at, rest)
    date = _day_date(day, local_now)
    if date is None:
        return None
    if tod is None:
        if tonight or part:
            return None  # "tomorrow morning" has no exact time: ask
        tod = DEFAULT_HOUR
    fire_at = datetime.combine(date, tod, tzinfo=tz)
    if fire_at <= local_now:
        return None  # "today at" a time that has gone: ask, do not roll over
    return ParsedReminder(fire_at, rest)
