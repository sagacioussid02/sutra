"""Which language the user is speaking, and the fixed replies in Hindi.

Only the few fixed messages on the confirmation, offer and reminder paths are translated here; everything
else is written by the model in the language the user used. Detection is deliberately cheap and decided in
code, because it picks safe fixed replies and switches humor off.
"""

from __future__ import annotations

import re

DEVANAGARI = re.compile(r"[ऀ-ॿ]")
_LETTER = re.compile(r"[^\W\d_]", re.UNICODE)
# Common Hinglish (Hindi in Latin letters) words that are not English words.
HINGLISH = frozenset(
    """hai hain haan nahi nahin nhi kya mujhe mujhko aap tum kal aaj baje karo karna kar dena yaad dila dilana dilao
    mera meri mere batao bataiye accha achha theek thik bahut abhi kuch kaise kyun kyu chahiye lagao lagana shaam
    subah raat dopahar ghante ghanta baad bilkul zaroor pata lekin magar toh bhi nahi na ruko rehne rahne""".split()
)
_WORD = re.compile(r"[a-z']+")


def detect(text: str) -> str:
    """"hi" for Hindi or Hinglish, "en" otherwise."""
    letters = _LETTER.findall(text)
    if not letters:
        return "en"
    if len(DEVANAGARI.findall(text)) / len(letters) >= 0.30:
        return "hi"
    words = _WORD.findall(text.lower())
    hits = {w for w in words if w in HINGLISH} - {"na", "toh", "kar", "do", "pata"}
    return "hi" if len(hits) >= 2 or (len(hits) == 1 and len(words) <= 3) else "en"


# English fixed reply -> Hindi. Worded to be neutral about the speaker's gender.
HI: dict[str, str] = {
    "Okay, I won't do that. Nothing was changed.": "ठीक है, यह नहीं किया जाएगा। कुछ भी नहीं बदला।",
    "That request expired, so nothing was done. Just ask again if you still want it.": "यह अनुरोध समाप्त हो गया, इसलिए कुछ नहीं किया गया। अगर अब भी चाहिए तो फिर से बोलिए।",
    "I'll leave that for now. Nothing was done.": "ठीक है, इसे अभी छोड़ देते हैं। कुछ नहीं किया गया।",
    "Okay, I'll leave that for now. Nothing was done.": "ठीक है, अभी छोड़ देते हैं। कुछ नहीं किया गया।",
    "Sorry, I didn't quite get that. Was that a yes or a no?": "माफ़ कीजिए, समझ नहीं आया। हाँ था या नहीं?",
    "Sorry, I didn't catch that. Was that a yes or a no?": "माफ़ कीजिए, सुनाई नहीं दिया। हाँ था या नहीं?",
    "Okay, I won't bring that up again.": "ठीक है, अब इसकी बात नहीं करेंगे।",
    "Okay, I'll hold off on that.": "ठीक है, अभी रहने देते हैं।",
    "Okay, I won't ask about that.": "ठीक है, इस बारे में नहीं पूछेंगे।",
    "I'm already working on a couple of things. Give me a moment.": "अभी दो काम चल रहे हैं। थोड़ी देर बाद फिर पूछिए।",
}


def localize(reply: str, lang: str) -> str:
    """The Hindi version of a fixed reply when the user spoke Hindi; otherwise the reply unchanged."""
    return HI.get(reply, reply) if lang == "hi" else reply


def reask(description: str, lang: str) -> str:
    if lang == "hi":
        return f"माफ़ कीजिए, समझ नहीं आया। {description} क्या आगे बढ़ूँ? कृपया हाँ या नहीं कहिए।"
    return f"Sorry, I wasn't sure what you meant. {description} Should I go ahead? Please say yes or no."


def heard(text: str, lang: str) -> str:
    return f"मैंने सुना: {text}।" if lang == "hi" else f"I heard: {text}."
