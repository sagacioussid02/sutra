"""One mode that everything consults: full, limited, or off. The voice can lower it; only a keyboard can raise it.

The mode is decided and enforced in code, saved to a private file, and fails safe: an unreadable file means
limited. Nothing here asks the model whether something is allowed.
"""

from __future__ import annotations

import json
import logging
import os
import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

log = logging.getLogger("sutra_orchestrator")

MODE_FILE = "mode.json"
READ_VERBS = frozenset("get list read show find search describe view status check".split())
LOCAL_BLOCKED = frozenset({"delegate_research"})  # the one local tool that spends money


class Mode(str, Enum):
    FULL = "full"
    LIMITED = "limited"
    OFF = "off"


RANK = {Mode.OFF: 0, Mode.LIMITED: 1, Mode.FULL: 2}

OFF_REPLY = "I'm switched off. Use the keyboard to turn me back on: type /mode full, or press f."
OFF_REPLY_HI = "मैं बंद हूँ। मुझे वापस चालू करने के लिए कीबोर्ड इस्तेमाल कीजिए: /mode full लिखिए, या f दबाइए।"
LIMITED_REPLY = "Okay, limited mode. I'll only look things up: no changes, nothing unprompted. Use the keyboard to go back to full."
LIMITED_REPLY_HI = "ठीक है, सीमित मोड। मैं सिर्फ़ जानकारी देखूँगा: कोई बदलाव नहीं, अपने आप कुछ नहीं। पूरे मोड में लौटने के लिए कीबोर्ड इस्तेमाल कीजिए।"
RAISE_REPLY = "I can't be switched up by voice. Use the keyboard: type /mode full, or press f."
RAISE_REPLY_HI = "आवाज़ से मुझे चालू नहीं किया जा सकता। कीबोर्ड इस्तेमाल कीजिए: /mode full लिखिए, या f दबाइए।"
DROPPED_REPLY = "I'm not in full mode, so I didn't do that. Nothing was changed."
DROPPED_REPLY_HI = "मैं पूरे मोड में नहीं हूँ, इसलिए यह नहीं किया गया। कुछ भी नहीं बदला।"

_LEAD = r"^\W*(?:(?:hey|ok|okay)\s+)?(?:sutra\W+)?(?:please\s+)?"
_TAIL = r"(?:\s+(?:please|now|for now))?\W*$"
_LIMITED = re.compile(
    _LEAD + r"(?:(?:go\s+(?:in)?to|switch\s+to|enter|turn\s+on|use)\s+)?(?:safe|limited|read[- ]only)\s+mode" + _TAIL
    + r"|^\W*(?:सेफ मोड|सुरक्षित मोड|लिमिटेड मोड|सीमित मोड|safe mode kar do|limited mode (?:kar do|lagao))\W*$",
    re.IGNORECASE)
_OFF = re.compile(
    _LEAD + r"(?:go\s+quiet|be\s+quiet(?:\s+now)?|mute\s+yourself|stop\s+listening|switch\s+(?:yourself\s+)?off|"
    r"turn\s+yourself\s+off|shut\s+(?:yourself\s+)?down|power\s+off)" + _TAIL
    + r"|^\W*(?:चुप हो जाओ|चुप हो जाइए|सुनना बंद करो|बंद हो जाओ|chup ho jao|sunna band karo)\W*$",
    re.IGNORECASE)
_RAISE = re.compile(
    _LEAD + r"(?:(?:full|normal)\s+mode|unmute(?:\s+yourself)?|wake\s+up|come\s+back|turn\s+(?:yourself\s+)?on|switch\s+on)" + _TAIL,
    re.IGNORECASE)


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFC", text).lower().replace("'", "").replace("’", "")
    return " ".join(re.sub(r"[^\wऀ-ॿ\s]", " ", text).split())


@dataclass(frozen=True)
class Command:
    kind: str  # "keyword", "duress" or "raise_attempt"
    target: Mode | None
    announce: bool
    text: str  # the utterance with a distress phrase cut out; unchanged otherwise


class SafetyService:
    def __init__(
        self,
        directory: str | Path,
        *,
        start: Mode = Mode.FULL,
        extra_tools: tuple[str, ...] = (),
        duress_phrase: str = "",
    ) -> None:
        self._path = Path(directory) / MODE_FILE
        self._start = start
        self._extra = frozenset(extra_tools)
        self._duress = _norm(duress_phrase)
        self._duress_re = (
            re.compile(r"(?<!\w)" + r"\W+".join(map(re.escape, self._duress.split())) + r"(?!\w)", re.IGNORECASE)
            if self._duress else None
        )
        self._listeners: list[Callable[[Mode], None]] = []
        self._mode = self._load()
        self.silent = False  # the distress phrase lowered it: never say why

    # ------------------------------------------------------------------ state

    def _load(self) -> Mode:
        try:
            raw = self._path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return self._start
        except OSError:
            return Mode.LIMITED
        try:
            return Mode(json.loads(raw)["mode"])
        except (ValueError, KeyError, TypeError):
            return Mode.LIMITED  # damaged: fail safe

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump({"mode": self._mode.value}, f)
        os.replace(tmp, self._path)

    @property
    def mode(self) -> Mode:
        return self._mode

    @property
    def proactive_ok(self) -> bool:
        """Unprompted speech, spending, outside requests and the group chat: full mode only."""
        return self._mode is Mode.FULL

    def on_change(self, listener: Callable[[Mode], None]) -> None:
        self._listeners.append(listener)

    def _set(self, mode: Mode) -> None:
        if mode is self._mode:
            return
        self._mode = mode
        self._save()
        log.info("mode is now %s", mode.value)
        for listener in self._listeners:
            try:
                listener(mode)
            except Exception:
                log.debug("a mode listener failed", exc_info=True)

    def lower(self, to: Mode) -> bool:
        """Drop to a lower mode. Used by the voice and by anything automatic; it can never raise."""
        if RANK[to] >= RANK[self._mode]:
            return False
        self._set(to)
        return True

    def restore(self, to: Mode) -> None:
        """Set any mode. For the keyboard only: a typed command or a key press, never a spoken phrase."""
        self.silent = False
        self._set(to)

    # --------------------------------------------------------------- commands

    def command(self, text: str) -> Command | None:
        """A spoken or typed mode keyword, or the private distress phrase, found in ``text``."""
        if self._duress_re is not None and self._duress_re.search(text):
            cleaned = " ".join(self._duress_re.sub(" ", text).split())
            cleaned = re.sub(r"\s*[,;][\s,;!?.]*", ", ", cleaned).strip(" ,.;!?")
            return Command("duress", Mode.LIMITED, False, cleaned)
        if _OFF.match(text):
            return Command("keyword", Mode.OFF, True, text)
        if _LIMITED.match(text):
            return Command("keyword", Mode.LIMITED, True, text)
        if self._mode is not Mode.FULL and _RAISE.match(text):
            return Command("raise_attempt", None, True, text)
        return None

    # ------------------------------------------------------------------ tools

    def tool_allowed(self, name: str, *, local: bool) -> bool:
        if self._mode is Mode.FULL:
            return True
        if self._mode is Mode.OFF:
            return False
        if local:
            return name not in LOCAL_BLOCKED
        if name in self._extra:
            return True
        _, _, rest = name.partition("_")
        verb = (rest or name).split("_", 1)[0]
        return bool(rest) and verb in READ_VERBS  # fail closed: anything not clearly a read is blocked
