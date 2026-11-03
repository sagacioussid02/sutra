"""Hindi and Hinglish reminder requests, rewritten into the form the deterministic parser already reads.

"मुझे 5 मिनट बाद याद दिलाना कि चाय बनानी है" becomes "in 5 minutes to चाय बनानी है". The reminder text stays in
the user's own words; only the time is translated. Anything this cannot pin down returns an empty request, so the
caller asks, instead of guessing.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from zoneinfo import ZoneInfo

_ND = r"(?<![ऀ-ॿ\w])"  # \b does not work next to Devanagari vowel signs
_NA = r"(?![ऀ-ॿ\w])"

_NUMBERS = {
    "ek": 1, "एक": 1, "do": 2, "दो": 2, "teen": 3, "तीन": 3, "char": 4, "chaar": 4, "चार": 4, "paanch": 5, "panch": 5,
    "पाँच": 5, "पांच": 5, "chhe": 6, "chhah": 6, "cheh": 6, "छह": 6, "छः": 6, "saat": 7, "सात": 7, "aath": 8, "आठ": 8,
    "nau": 9, "नौ": 9, "das": 10, "दस": 10, "gyarah": 11, "ग्यारह": 11, "barah": 12, "बारह": 12,
    "pandrah": 15, "पंद्रह": 15, "bees": 20, "बीस": 20, "pachees": 25, "पच्चीस": 25, "tees": 30, "तीस": 30,
}
_NUM = "|".join(sorted(map(re.escape, _NUMBERS), key=len, reverse=True))
_T = r"[\u0900-\u097f\w]*"  # the rest of a word (Devanagari vowel signs are not \w)
_GIVE = r"(?:\s+(?:dena|do|dijiye|dijiyega|diya|karo|देना|दो|दीजिए|दीजिएगा))?"
_LEAD = re.compile(
    _ND + r"(?:(?:yaad|yad)\s*dila" + _T + _GIVE + r"|याद\s*दिला" + _T + _GIVE
    + r"|reminder\s*(?:laga|set|lagao)" + _T + r"(?:\s*(?:kar|karo|do|dena))*"
    r"|रिमाइंडर\s*(?:लगा|सेट)" + _T + r"(?:\s*(?:कर|करो|दो|देना))*)" + _NA, re.IGNORECASE)
_ME = re.compile(_ND + r"(?:mujhe|mujhko|mujhse|मुझे|मुझको)" + _NA, re.IGNORECASE)
_THAT = re.compile(_ND + r"(?:ki|कि|ke\s*liye|के\s*लिए)" + _NA, re.IGNORECASE)
_HALF = re.compile(
    _ND + r"(?:aadha|adha|आधा|आधे)\s*(?:ghante|ghanta|ghantey|घंटे|घंटा)(?:\s*(?:ke\s*)?(?:baad|बाद|mein|में|के\s*बाद))?" + _NA,
    re.IGNORECASE)
_REL = re.compile(
    _ND + rf"(?P<n>\d+|{_NUM})\s*(?P<u>minute|minat|min|मिनट|ghante|ghanta|ghantey|घंटे|घंटा|hour|hours)\s*"
    r"(?:ke\s*)?(?:baad|बाद|mein|में|के\s*बाद)" + _NA, re.IGNORECASE)
_AT = re.compile(
    _ND + rf"(?P<h>\d{{1,2}}(?::\d{{2}})?|{_NUM})\s*(?:baje|bje|बजे)" + _NA, re.IGNORECASE)
_TODAY = re.compile(_ND + r"(?:aaj|आज)" + _NA, re.IGNORECASE)
_TOMORROW = re.compile(_ND + r"(?:kal|कल)" + _NA, re.IGNORECASE)
_PARSO = re.compile(_ND + r"(?:parso|परसों)" + _NA, re.IGNORECASE)
_PARTS = [
    (re.compile(_ND + r"(?:subah|subha|सुबह)" + _NA, re.IGNORECASE), "in the morning"),
    (re.compile(_ND + r"(?:dopahar|दोपहर)" + _NA, re.IGNORECASE), "in the afternoon"),
    (re.compile(_ND + r"(?:shaam|sham|शाम)" + _NA, re.IGNORECASE), "in the evening"),
    (re.compile(_ND + r"(?:raat|rat|रात)" + _NA, re.IGNORECASE), "at night"),
]
_FILLER = re.compile(_ND + r"(?:please|plz|zara|ज़रा|जरा|zaroor|जरूर)" + _NA, re.IGNORECASE)


def _number(token: str) -> int:
    return int(token) if token.isdigit() else _NUMBERS[token.lower()]


def hindi_request(utterance: str) -> str | None:
    """None if this is not a Hindi or Hinglish reminder request.

    "" if it is one but the time cannot be pinned down (the caller asks). Otherwise the request in the
    English form the parser reads, such as "in 5 minutes to chai banani hai" or "tomorrow at 9 in the morning to ...".
    """
    text = unicodedata.normalize("NFC", utterance).replace("।", " ").strip()
    if not _LEAD.search(text):
        return None
    spans: list[tuple[int, int]] = []

    def take(pattern: re.Pattern[str]) -> re.Match[str] | None:
        m = pattern.search(text)
        if m:
            spans.append(m.span())
        return m

    take(_LEAD)
    take(_ME)
    when: str | None = None
    if m := take(_HALF):
        when = "in half an hour"
    elif m := take(_REL):
        n, unit = _number(m.group("n")), m.group("u").lower()
        hours = unit in ("ghante", "ghanta", "ghantey", "घंटे", "घंटा", "hour", "hours")
        when = "in an hour" if hours and n == 1 else f"in {n} {'hours' if hours else 'minutes'}"
    else:
        day = "today" if take(_TODAY) else "tomorrow" if take(_TOMORROW) else ""
        if _PARSO.search(text):
            return ""  # the day after tomorrow: not supported, so ask rather than guess
        part = ""
        for pattern, words in _PARTS:
            if take(pattern):
                part = words
                break
        at = take(_AT)
        if at:
            raw = at.group("h")
            hour = raw if raw[0].isdigit() else str(_number(raw))
            when = " ".join(x for x in (day, f"at {hour}", part) if x)
        else:
            return ""  # a day or part of day with no hour ("kal subah"), or no time at all
    take(_THAT)
    take(_FILLER)
    rest = list(text)
    for a, b in sorted(spans, reverse=True):
        rest[a:b] = " "
    body = " ".join("".join(rest).split()).strip(" ,.;:!?")
    body = re.sub(rf"^(?:{_ND}(?:ki|कि|ko|को|toh|तो)\s+)+", "", body, flags=re.IGNORECASE).strip()
    if not body:
        return ""
    return f"{when} to {body}"


_WEEKDAYS = ["सोमवार", "मंगलवार", "बुधवार", "गुरुवार", "शुक्रवार", "शनिवार", "रविवार"]
_MONTHS = ["जनवरी", "फ़रवरी", "मार्च", "अप्रैल", "मई", "जून", "जुलाई", "अगस्त", "सितंबर", "अक्टूबर", "नवंबर", "दिसंबर"]


def spoken_when_hi(fire_at: datetime, now: datetime, tz: ZoneInfo) -> str:
    """"कल सुबह 9:00 बजे" from a fire time."""
    local = fire_at.astimezone(tz)
    today = now.astimezone(tz).date()
    days = (local.date() - today).days
    day = "आज" if days == 0 else "कल" if days == 1 else (
        f"{_WEEKDAYS[local.weekday()]} को" if days < 7 else f"{local.day} {_MONTHS[local.month - 1]} को")
    h = local.hour
    part = "सुबह" if 4 <= h < 12 else "दोपहर" if 12 <= h < 16 else "शाम" if 16 <= h < 20 else "रात"
    h12 = h % 12 or 12
    return f"{day} {part} {h12}:{local.minute:02d} बजे"
