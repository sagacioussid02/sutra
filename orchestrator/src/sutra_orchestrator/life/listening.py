"""Listening mode: when someone wants to talk, not to be fixed. Detected in code, on the user's own words."""

from __future__ import annotations

import re

LISTEN_TURNS = 5

_VENT = re.compile(
    r"\b(rough day|bad day|terrible day|awful day|long day|need to vent|want to vent|just want to talk|"
    r"can i (?:just )?talk|need to talk|wanna talk|could we (?:just )?talk|i feel (?:so )?(?:sad|down|low|anxious|"
    r"lonely|alone|overwhelmed|empty|lost|stuck|hopeless|worthless)|i'?m (?:feeling )?(?:so )?(?:sad|down|lonely|"
    r"overwhelmed|anxious|depressed|burnt out|burned out|exhausted)|had a hard time|having a hard time|"
    r"feeling (?:really )?(?:sad|low|down|lonely|anxious|overwhelmed))\b",
    re.IGNORECASE,
)
_CRISIS = re.compile(
    r"\b(want(?:ed|ing)? to die|wanna die|wish i (?:was|were) dead|wish i (?:was|were)n'?t (?:here|alive)|"
    r"kill(?:ing)? myself|(?:end|ending|ended|take|taking) (?:my (?:own )?life|it all)|suicid\w*|"
    r"(?:hurt|hurting|harm|harming)(?: myself)|(?:cut|cutting) myself(?! (?:some|a|off|out|loose|short)\b)|self.?harm|"
    r"(?:don'?t|do not|no longer) want to (?:be here|live|exist|be alive|wake up)|"
    r"no (?:reason|point) (?:to|in) (?:live|living|go on|going on)|can'?t go on(?: like this| anymore| any more| any longer|[.!]|$)|can'?t do this anymore|"
    r"better off (?:dead|without me)|want(?:ed|ing)? to (?:just )?disappear(?! (?:into|for|from|on|to|in)\b)|not worth living)\b",
    re.IGNORECASE,
)
_ND, _NA = r"(?<![\u0900-\u097f\w])", r"(?![\u0900-\u097f\w])"
_VENT_HI = re.compile(
    _ND + r"(?:mann? kharab|मन खराब|udaas|उदास|akela mehsoos|अकेला महसूस|akelapan|अकेलापन|bura din|बुरा दिन|baat karni hai|"
    r"बात करनी है|baat karna chahta|baat karna chahti|बात करना चाहता|बात करना चाहती|dil bhaari|दिल भारी|bahut pareshan|"
    r"बहुत परेशान|ghabrahat|घबराहट|thak gaya hoon|thak gayi hoon|थक गया हूँ|थक गई हूँ|rona aa raha|रोना आ रहा)" + _NA,
    re.IGNORECASE)
_CRISIS_HI = re.compile(
    _ND + r"(?:marna chahta|marna chahti|मरना चाहता|मरना चाहती|jeena nahi chahta|jeena nahi chahti|जीना नहीं चाहता|"
    r"जीना नहीं चाहती|jeene ka mann nahi|जीने का मन नहीं|khud ko khatam|खुद को खत्म|apni jaan|अपनी जान|aatmahatya|आत्महत्या|"
    r"zindagi khatam|ज़िंदगी खत्म|जिंदगी खत्म|khud ko nuksan|खुद को नुकसान|suicide)" + _NA, re.IGNORECASE)
_GREETING = re.compile(r"^\W*(hi|hey|hello|yo|good (?:morning|afternoon|evening)|morning|evening|how are you|"
                       r"how'?s it going|what'?s up|sup)\b", re.IGNORECASE)

LISTEN_NOTE = (
    "The user wants to talk, not to be fixed. Do not give lists, steps or solutions, and give advice only if "
    "they ask for it. Reflect back what you heard in their own terms, and ask at most one gentle question. Do not "
    "joke. Keep it short and warm, like a friend who is simply there. You are not a therapist; mention that only "
    "if it truly matters."
)
CRISIS_NOTE_HI_EXTRA = (
    " If they are in India: Tele-MANAS, the national mental health helpline, is free at 14416, and 112 is the "
    "emergency number. Reply in the language they used."
)
CRISIS_NOTE = (
    "The user may be thinking about ending their life or hurting themselves. Respond with warmth first: say you are "
    "glad they told you and that you take it seriously. Gently encourage them to reach out right now to someone they "
    "trust, and to a crisis line or emergency services (in the United States, call or text 988 for the Suicide and "
    "Crisis Lifeline, or call 911 if they are in immediate danger; elsewhere, their local emergency number). Ask if "
    "they are safe right now. Stay with them. Never give methods or instructions, and do not lecture or minimize."
)


def is_vent(text: str) -> bool:
    return bool(_VENT.search(text) or _VENT_HI.search(text))


def is_crisis(text: str) -> bool:
    return bool(_CRISIS.search(text) or _CRISIS_HI.search(text))


def is_greeting(text: str) -> bool:
    return len(text.split()) <= 6 and bool(_GREETING.match(text.strip()))
