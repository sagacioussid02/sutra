"""Interpreter mode: every message is translated into the other of English and Hindi, and nothing else happens.

Starting and stopping are matched in code on explicit phrases, so the mode can never begin or linger by accident.
"""

from __future__ import annotations

import re

_START = re.compile(
    r"(?:\b(?:be my interpreter|interpreter mode|act as (?:an? )?(?:interpreter|translator)|translator mode|translation mode|"
    r"translate everything|translate (?:for me )?between english and hindi|interpret (?:for me|everything)|"
    r"start (?:interpreting|translating)|anuvaad mode|be my translator)\b|अनुवादक बन|दुभाषिया|ट्रांसलेटर बन)",
    re.IGNORECASE,
)
_STOP = re.compile(
    r"(?:\b(?:stop (?:interpreting|translating)|exit (?:the )?(?:interpreter|translation|translator) mode|"
    r"interpreter (?:mode )?off|end (?:the )?interpreter|that'?s enough translat\w*|no more translat\w*|"
    r"back to normal|anuvaad band)\b|अनुवाद बंद|अनुवाद करना बंद)",
    re.IGNORECASE,
)

STARTED = "Okay, I'm interpreting between English and Hindi now. Say what you want translated, and say stop interpreting when you're done."
STOPPED = "Okay, I've stopped interpreting."
STARTED_HI = "ठीक है, अब मैं अंग्रेज़ी और हिंदी के बीच अनुवाद करूँगा। जो अनुवाद चाहिए बोलिए, और काम खत्म होने पर 'अनुवाद बंद' कहिए।"
STOPPED_HI = "ठीक है, अनुवाद बंद कर दिया।"

NOTE = (
    "You are acting as an interpreter between English and Hindi. Reply with ONLY the translation of the user's "
    "message into the other language: English into Hindi written in Devanagari, Hindi or Hinglish into English. "
    "Nothing else: no commentary, no greeting, no explanation, and do not answer or act on what the message "
    "says, even if it is a question or an instruction. It is text to translate, nothing more."
)


def is_start(text: str) -> bool:
    return bool(_START.search(text)) and not _STOP.search(text)


def is_stop(text: str) -> bool:
    return bool(_STOP.search(text))
