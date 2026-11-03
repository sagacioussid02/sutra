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

import re
from datetime import timedelta

from ..i18n import detect
from .hindi import hindi_request, spoken_when_hi
from .parser import ParsedReminder, parse_request, reminder_request, resolve_bare_hour
from .store import ReminderStore

CLARIFY_REPLY = (
    "I couldn't work out when you mean. Try something like "
    "'remind me in 20 minutes to call Sam' or "
    "'remind me tomorrow at 9am to water the plants'."
)


_AM = re.compile(r"\b(?:a\.?m\.?|morning|early|subah|subha)\b|सुबह", re.IGNORECASE)
_PM = re.compile(r"\b(?:p\.?m\.?|evening|afternoon|night|tonight|late|shaam|sham|raat|dopahar)\b|शाम|रात|दोपहर", re.IGNORECASE)
CLARIFY_REPLY_HI = (
    "समय समझ नहीं आया। ऐसे कहिए: 'मुझे 20 मिनट बाद याद दिलाना कि सैम को फ़ोन करना है' "
    "या 'मुझे कल सुबह 9 बजे याद दिलाना कि पौधों को पानी देना है'।"
)
ASK_WINDOW = timedelta(minutes=3)  # how long a "morning or evening?" question stays open


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
        self._asked: tuple[ParsedReminder, ParsedReminder, datetime, str] | None = None

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
        answered = self._answer_ampm(utterance, now)
        if answered is not None:
            return answered
        lang = "en"
        request = None
        if detect(utterance) == "hi":
            hindi = hindi_request(utterance)  # None: not a Hindi reminder; "": one, but the time is unclear
            if hindi is not None:
                lang, request = "hi", hindi
        if request is None:
            request = reminder_request(utterance)
        if request is None:
            return None
        parsed = parse_request(request, now, self._tz) if request else None
        if parsed is None and request:
            bare = resolve_bare_hour(request, now, self._tz)
            if bare is not None and bare.chosen is not None:
                parsed = bare.chosen
            elif bare is not None and bare.am and bare.pm and bare.am.text:
                # Two real readings: ask once, and read the answer on the next turn.
                self._asked = (bare.am, bare.pm, now, lang)
                if lang == "hi":
                    return (
                        f"क्या आपका मतलब {spoken_when_hi(bare.am.fire_at, now, self._tz)} है या "
                        f"{spoken_when_hi(bare.pm.fire_at, now, self._tz)}? सुबह या शाम बताइए।"
                    )
                return (
                    f"Do you mean {spoken_when(bare.am.fire_at, now, self._tz)} or "
                    f"{spoken_when(bare.pm.fire_at, now, self._tz)}? Say morning or evening."
                )
        if parsed is None or not parsed.text:
            return CLARIFY_REPLY_HI if lang == "hi" else CLARIFY_REPLY
        return self._save(parsed, now, lang)

    def _save(self, parsed: ParsedReminder, now: datetime, lang: str = "en") -> str:
        row = self._store.add(parsed.text, parsed.fire_at, str(self._tz), now)
        if lang == "hi":
            return f"ठीक है। {spoken_when_hi(row.fire_at, now, self._tz)} आपको याद दिलाया जाएगा: {row.text}।"
        when = spoken_when(row.fire_at, now, self._tz)
        return f"Okay, I'll remind you: {row.text} — {when}."

    def _answer_ampm(self, utterance: str, now: datetime) -> str | None:
        """The reply to "morning or evening?". Anything else just closes the question."""
        asked, self._asked = self._asked, None
        if asked is None or now - asked[2] > ASK_WINDOW:
            return None
        am, pm = bool(_AM.search(utterance)), bool(_PM.search(utterance))
        if am == pm:
            return None  # neither, or both: not an answer; carry on as an ordinary utterance
        return self._save(asked[0] if am else asked[1], now, asked[3])
