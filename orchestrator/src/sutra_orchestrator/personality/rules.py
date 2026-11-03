"""When humor is never offered. Decided in code: a prompt asking the model to judge this would not be reliable."""

from __future__ import annotations

import re

_HEAVY = re.compile(
    r"\b(money|debts?|loans?|mortgage|bankrupt\w*|owe[sd]?|broke|bills?|rent|salary|taxes|"
    r"sick|ill|illness|cancer|hospital|doctor|surgery|pain|diagnos\w*|medic\w*|chemo\w*|injur\w*|"
    r"anxiety|anxious|depress\w*|therapy|panic|"
    r"died|death|dead|dying|passed away|funeral|grief|grieving|"
    r"divorce\w*|breakup|broke up|separated|custody|"
    r"lawsuit|lawyer|arrest\w*|police|court|sued|"
    r"suicid\w*|self.harm|kill myself|abus\w*|emergency|hurt myself)\b",
    re.IGNORECASE,
)
_UPSET = re.compile(
    r"\b(ugh+|annoying|annoyed|frustrat\w*|stupid|hate|angry|furious|stressed|stressful|worried|sad|upset|"
    r"tired of|sick of|fed up|not funny|stop joking|overwhelm\w*|exhausted|terrible|awful|"
    r"this is so|why (?:won't|can't|doesn't|isn't)|so slow|useless)\b",
    re.IGNORECASE,
)
# The same nets in Hindi and Hinglish. \b does not work beside Devanagari vowel signs, so explicit edges.
_ND, _NA = r"(?<![\u0900-\u097f\w])", r"(?![\u0900-\u097f\w])"
_HEAVY_HI = re.compile(
    _ND + r"(?:bimaar\w*|bimari|बीमार\w*|बीमारी|aspatal|अस्पताल|maut|मौत|mrityu|मृत्यु|nidhan|निधन|karz\w*|कर्ज़\w*|कर्ज\w*|"
    r"talaak|तलाक|jhagda|झगड़ा|adalat|अदालत|vakeel|वकील|sadma|सदमा|paise ki tangi|पैसे की तंगी|marna|मरना|"
    r"saans ki takleef|कैंसर|cancer|operation|ऑपरेशन)" + _NA, re.IGNORECASE)
_UPSET_HI = re.compile(
    _ND + r"(?:pareshan\w*|परेशान\w*|udaas|उदास|gussa|गुस्सा|tang aa gaya|तंग आ|thak gaya|थक गया|thak gayi|थक गई|"
    r"bura lag\w*|बुरा लग\w*|ghabra\w*|घबरा\w*|dukhi|दुखी|chidh\w*|चिढ़\w*|bekaar|बेकार|nafrat|नफ़रत|nafrat)" + _NA,
    re.IGNORECASE)
QUIET_TURNS = 3  # after something heavy or upsetting, this many more turns stay serious


def heavy(text: str) -> bool:
    return bool(_HEAVY.search(text) or _HEAVY_HI.search(text))


def upset(text: str) -> bool:
    return bool(_UPSET.search(text) or _UPSET_HI.search(text))
