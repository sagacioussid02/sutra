"""One-time questions drawn from the user's own recent activity, behind a feature flipper.

The user earns a higher mode, or a ten-minute grant for protected tools, by answering questions that are different
every time. A fact that has been asked about is retired, so an overheard question and answer is useless later. The
question text, the outcomes and every reply are fixed or code-checked: the main model never writes any part of the check.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from ..safety import Mode, SafetyService
from .filters import usable
from .judge import MATCH, AnswerJudge
from .questions import Question, QuestionWriter
from .store import AuthStore, Fact

log = logging.getLogger("sutra_orchestrator")

GRANT = timedelta(minutes=10)
CHALLENGE_TIMEOUT = timedelta(minutes=2)
COOLDOWN = timedelta(minutes=15)
LONG_COOLDOWN = timedelta(hours=1)
MAX_WRONG = 2
MIN_FACTS = {"mode": 4, "action": 6}
MIN_DAYS = 2

PREFIX = "To check it's you: "
RETRY = "That doesn't match. Let me try another. "
NEXT = "That's right. One more: "
PASSED_MODE = "Thanks, that's right. I'm back in full mode."
PASSED_ACTION = "Thanks, you're verified for ten minutes. Ask me again and I'll take it from there."
FAILED = "That doesn't match, so I'm staying in limited mode for now. Use the keyboard to bring me back."
CANCELLED = "Okay, cancelled."
NO_DATA = "I can't verify you right now. Use the keyboard to do that."
LOCKED = "I'm not taking verification attempts for a while. Use the keyboard if you need me sooner."
_CANCEL = re.compile(r"^\W*(?:cancel|never ?mind|forget it|stop|रहने दो|छोड़ो)\W*$", re.IGNORECASE)

# Outcomes
ASK, PASSED, FAILED_OUT, CANCELLED_OUT, REFUSED, DURESS = "ask", "passed", "failed", "cancelled", "refused", "duress"


@dataclass(frozen=True)
class AuthReply:
    text: str
    outcome: str
    purpose: str = ""


@dataclass
class _Challenge:
    purpose: str  # "mode" or "action"
    need: int
    started: datetime
    right: int = 0
    wrong: int = 0
    kinds: list[str] = field(default_factory=list)
    current: Question | None = None
    touched: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


RawFacts = Callable[[datetime], list[tuple[str, str, str, datetime]]]  # (ref, text, kind, ts)


class AuthService:
    def __init__(
        self,
        store: AuthStore,
        writer: QuestionWriter,
        judge: AnswerJudge,
        safety: SafetyService,
        *,
        tz: ZoneInfo,
        names: Callable[[], list[str]] = lambda: [],
        extra_facts: list[RawFacts] | None = None,
        default_enabled: bool = False,
        mode_questions: int = 1,
        action_need: int = 2,
        protected: tuple[str, ...] | None = None,  # None: every gateway tool that is not a reader
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._store = store
        self._writer = writer
        self._judge = judge
        self._safety = safety
        self._tz = tz
        self._names = names
        self._extra = extra_facts or []
        self._default = default_enabled
        self._mode_need = mode_questions
        self._action_need = action_need
        self._protected = protected
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._challenge: _Challenge | None = None
        self._used_refs: dict[str, Fact] = {}

    @property
    def store(self) -> AuthStore:
        return self._store

    # ---------------------------------------------------------------- the flipper

    @property
    def enabled(self) -> bool:
        stored = self._store.get_meta("enabled")
        return self._default if stored is None else stored == "1"

    def set_enabled(self, on: bool) -> None:
        """The keyboard turns it on or off. Turning it off ends any challenge and any grant."""
        self._store.set_meta("enabled", "1" if on else "0")
        if not on:
            self._challenge = None
            self._store.set_meta("grant_until", "")

    # --------------------------------------------------------------------- facts

    def observe(self, utterance: str, via: str, low_confidence: bool = False) -> None:
        """Keep a safe piece of the user's own words as a possible question source."""
        if not self.enabled or low_confidence:
            return
        text = " ".join(utterance.split())
        if usable(text, self._names()):
            self._store.add_fact(text, "typed" if via == "text" else "spoken", self._now())

    def facts(self) -> list[Fact]:
        """Usable facts, typed first and then newest, from the bank, reminders and plans."""
        now = self._now()
        names = self._names()
        out = list(self._store.facts(now))
        for source in self._extra:
            try:
                for ref, text, kind, ts in source(now):
                    if not self._store.is_burned(ref) and usable(text, names, personal=False):
                        out.append(Fact(ref, text, kind, ts))
            except Exception:
                log.debug("a fact source failed", exc_info=True)
        out.sort(key=lambda f: (f.kind != "typed", -f.ts.timestamp()))
        return out

    def _enough(self, purpose: str) -> bool:
        facts = self.facts()
        days = {f.ts.astimezone(self._tz).date() for f in facts}
        return len(facts) >= MIN_FACTS[purpose] and len(days) >= MIN_DAYS

    # ------------------------------------------------------------------ the state

    @property
    def active(self) -> bool:
        c = self._challenge
        if c is None:
            return False
        if self._now() - c.touched > CHALLENGE_TIMEOUT:
            self._challenge = None
            return False
        return True

    def cancel(self) -> None:
        self._challenge = None

    def has_grant(self) -> bool:
        raw = self._store.get_meta("grant_until")
        return bool(raw) and datetime.fromisoformat(raw) > self._now()

    def locked_until(self) -> datetime | None:
        raw = self._store.get_meta("locked_until")
        if not raw:
            return None
        until = datetime.fromisoformat(raw)
        return until if until > self._now() else None

    def protected(self, tool: str) -> bool:
        """Is this gateway tool one that needs a grant? Readers never do."""
        if not self.enabled:
            return False
        if self._protected is None:
            return not self._safety.tool_allowed_when_limited(tool)
        return tool in self._protected

    # ---------------------------------------------------------------- challenges

    async def begin(self, purpose: str) -> AuthReply:
        """Start a challenge for "mode" (return to full) or "action" (a grant for protected tools)."""
        if self.locked_until() is not None:
            return AuthReply(LOCKED, REFUSED, purpose)
        if not self._enough(purpose):
            return AuthReply(NO_DATA, REFUSED, purpose)
        need = self._mode_need if purpose == "mode" else self._action_need
        self._challenge = _Challenge(purpose, need, self._now(), touched=self._now())
        asked = await self._ask(PREFIX)
        return asked or self._refuse(purpose)

    def _refuse(self, purpose: str) -> AuthReply:
        self._challenge = None
        return AuthReply(NO_DATA, REFUSED, purpose)

    async def _ask(self, lead: str) -> AuthReply | None:
        c = self._challenge
        assert c is not None
        pool = [f for f in self.facts() if f.ref not in self._used_refs]
        fresh = [f for f in pool if f.kind not in c.kinds] or pool  # rotate kinds where possible
        question = await self._writer.write(fresh, self._names(), self._now())
        if question is None:
            return None
        self._store.burn(question.ref, self._now())  # used, whatever the answer
        self._used_refs[question.ref] = next(f for f in pool if f.ref == question.ref)
        c.current, c.touched = question, self._now()
        c.kinds.append(question.kind)
        return AuthReply(lead + question.text, ASK, c.purpose)

    async def answer(self, text: str) -> AuthReply | None:
        """The user's reply to the open question. None if no challenge is open (or it timed out)."""
        if not self.active:
            return None
        c = self._challenge
        assert c is not None and c.current is not None
        if _CANCEL.match(text):
            self._challenge = None
            return AuthReply(CANCELLED, CANCELLED_OUT, c.purpose)
        if self._safety.command(text) is not None and self._safety.command(text).kind == "duress":
            return self._duress(c)
        verdict = await self._judge.judge(c.current.text, c.current.answer, text)
        c.touched = self._now()
        if verdict == MATCH:
            c.right += 1
        else:
            c.wrong += 1
        if c.right >= c.need:
            return self._pass(c)
        if c.wrong >= MAX_WRONG:
            return self._fail(c)
        more = await self._ask(RETRY if verdict != MATCH else NEXT)
        if more is not None:
            return more
        # Ran out of safe questions part-way: a wrong answer so far is a failure, otherwise just stop.
        return self._fail(c) if c.wrong else self._refuse(c.purpose)

    # ------------------------------------------------------------------ outcomes

    def _pass(self, c: _Challenge) -> AuthReply:
        self._challenge = None
        self._store.set_meta("fails", "[]")
        if c.purpose == "mode":
            self._safety.raise_authenticated(Mode.FULL)
            return AuthReply(PASSED_MODE, PASSED, "mode")
        self._store.set_meta("grant_until", (self._now() + GRANT).isoformat())
        return AuthReply(PASSED_ACTION, PASSED, "action")

    def _fail(self, c: _Challenge) -> AuthReply:
        self._challenge = None
        now = self._now()
        recent = [datetime.fromisoformat(t) for t in json.loads(self._store.get_meta("fails") or "[]")]
        recent = [t for t in recent if now - t < timedelta(hours=1)] + [now]
        self._store.set_meta("fails", json.dumps([t.isoformat() for t in recent]))
        self._store.set_meta("locked_until", (now + (LONG_COOLDOWN if len(recent) >= 2 else COOLDOWN)).isoformat())
        self._safety.lower(Mode.LIMITED)
        return AuthReply(FAILED, FAILED_OUT, c.purpose)

    def _duress(self, c: _Challenge) -> AuthReply:
        """The distress phrase as an answer: it looks like a pass, and nothing is unlocked."""
        self._challenge = None
        self._safety.lower(Mode.LIMITED)
        self._safety.silent = True
        return AuthReply(PASSED_MODE if c.purpose == "mode" else PASSED_ACTION, DURESS, c.purpose)

    # ------------------------------------------------------------------- status

    def status(self) -> dict:
        locked = self.locked_until()
        return {
            "enabled": self.enabled,
            "facts": len(self.facts()),
            "days": len({f.ts.astimezone(self._tz).date() for f in self.facts()}),
            "locked_until": locked,
            "grant": self.has_grant(),
            "ready_mode": self._enough("mode"),
            "ready_action": self._enough("action"),
        }
