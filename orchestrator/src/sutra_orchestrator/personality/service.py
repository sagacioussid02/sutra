"""Humor as the rest of Sutra sees it: rules in code, a learned profile, a short optional note.

The model is never asked to decide *whether* a joke is appropriate; code decides, and then only invites
one. What happens next is read back from the user's reaction and nudges the profile by small steps.
"""

from __future__ import annotations

import asyncio
import logging
import math
import random
from dataclasses import dataclass
from typing import Any

from ..memory import LocalTool, ToolContext
from ..model import StructuredModel
from ..prompts import load_prompt
from . import rules
from .store import (
    LEVEL_MAX,
    REACTIONS,
    STYLES,
    PersonalityStore,
)

log = logging.getLogger("sutra_orchestrator")

ADJUST_TOOL = "adjust_humor"
CHANCE_DIVISOR = 24.0  # level / 24: level 3 is one eligible turn in eight
MIN_GAP = 3


@dataclass(frozen=True)
class HumorPlan:
    style: str
    note: str


class PersonalityService:
    def __init__(
        self,
        store: PersonalityStore,
        model: StructuredModel | None = None,
        *,
        rng: random.Random | None = None,
        timeout: float = 20.0,
    ) -> None:
        self._store = store
        self._model = model
        self._rng = rng or random.Random()
        self._timeout = timeout
        self._turn = 0
        self._last_offer_turn = -1000
        self._quiet_until = -1
        self._awaiting: tuple[str, str] | None = None  # (style, what Sutra said)
        self._tasks: set[asyncio.Task[None]] = set()

    @property
    def store(self) -> PersonalityStore:
        return self._store

    # ------------------------------------------------------------- eligibility

    def gap(self) -> int:
        level = self._store.level
        return MIN_GAP if level <= 0 else max(MIN_GAP, round(CHANCE_DIVISOR / level))

    def plan(
        self, user_text: str, *, action_pending: bool = False, has_note: bool = False, low_confidence: bool = False
    ) -> HumorPlan | None:
        """A plan for this turn, or None. Called once per turn, before the model writes anything."""
        self._turn += 1
        level = self._store.level
        if rules.heavy(user_text) or rules.upset(user_text):
            # This turn and the next few stay serious, which also covers what was said just before.
            self._quiet_until = self._turn + rules.QUIET_TURNS
        if (
            not self._store.enabled
            or level <= 0
            or action_pending
            or has_note
            or low_confidence
            or self._turn <= self._quiet_until
            or self._turn - self._last_offer_turn < self.gap()
        ):
            return None
        if self._rng.random() >= level / CHANCE_DIVISOR:
            return None
        style = self.choose_style()
        self._last_offer_turn = self._turn
        note = (
            "If it fits naturally, you may add one short, light touch of humor in this style: "
            f"{STYLES[style]}. One line at most, and only if something natural comes to mind; otherwise say "
            "nothing funny. Never joke about money, health, family, loss, or anything the user seems upset about."
        )
        return HumorPlan(style, note)

    def choose_style(self) -> str:
        """One style, by softmax over the scores: low variety sticks to what works, high tries others."""
        scores = self._store.scores()
        t = self._store.variety
        weights = {s: math.exp(scores[s] / t) for s in STYLES}
        pick = self._rng.random() * sum(weights.values())
        for style, w in weights.items():
            pick -= w
            if pick <= 0:
                return style
        return next(iter(STYLES))

    # ---------------------------------------------------------------- learning

    def remember(self, plan: HumorPlan, reply: str) -> None:
        """Humor was invited and the model replied: whether it joked is read from the user's next words."""
        self._awaiting = (plan.style, reply)

    def start_reaction(self, user_text: str) -> None:
        """Begin reading the user's reaction to the last reply, beside the new turn (no waiting)."""
        if self._awaiting is None or self._model is None:
            self._awaiting = None
            return
        style, said = self._awaiting
        self._awaiting = None
        try:
            task = asyncio.get_running_loop().create_task(self._react(style, said, user_text))
        except RuntimeError:
            return
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _react(self, style: str, said: str, user_text: str) -> None:
        assert self._model is not None
        try:
            raw = await asyncio.wait_for(
                self._model.structured(
                    name="humor_reaction",
                    system=load_prompt("humor_reaction.md"),
                    user=f"Sutra said: {said[:500]}\nThe person replied: {user_text[:300]}",
                ),
                timeout=self._timeout,
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.debug("humor reaction check failed (%s); nothing changed", type(exc).__name__)
            return
        self.apply_reaction(style, raw)

    def apply_reaction(self, style: str, raw: Any) -> None:
        if not isinstance(raw, dict):
            return
        if raw.get("stop") is True:
            self._store.set_level(0)  # they asked for no more jokes, whether or not one was made
            return
        reaction = raw.get("reaction")
        if raw.get("joked") is True and reaction in REACTIONS:
            self._store.record_reaction(style, reaction)

    async def flush(self) -> None:
        if self._tasks:
            await asyncio.gather(*list(self._tasks), return_exceptions=True)

    # ---------------------------------------------------------------- the tool

    def tools(self) -> list[LocalTool]:
        async def adjust(args: dict, context: ToolContext) -> str:
            return self.adjust(str(args.get("change") or ""))

        return [
            LocalTool(
                name=ADJUST_TOOL,
                description=(
                    "Change how often you joke, when the user asks: more or less humor, no jokes, or jokes "
                    "back on. Use only on their request."
                ),
                input_schema={
                    "type": "object",
                    "properties": {"change": {"type": "string", "enum": ["more", "less", "off", "on"]}},
                    "required": ["change"],
                },
                handler=adjust,
            )
        ]

    def adjust(self, change: str) -> str:
        s = self._store
        if change == "off":
            s.set_level(0)
            return "Humor is off. Tell the user you will stop joking."
        if change == "on":
            s.set_enabled(True)
            s.set_level(s.last_level)
            return "Humor is back on. Tell the user."
        if change == "more":
            return f"Humor is now at level {s.set_level(min(s.level + 1, LEVEL_MAX))} of {LEVEL_MAX}. Tell the user."
        if change == "less":
            return f"Humor is now at level {s.set_level(max(s.level - 1, 0))} of {LEVEL_MAX}. Tell the user."
        return "No change was made."
