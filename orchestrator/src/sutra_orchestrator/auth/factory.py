"""Build the authentication service from configuration (shared by the text and voice clients)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from ..config import Config
from ..life import LifeService
from ..reminders import ReminderStore
from ..safety import SafetyService
from .judge import AnswerJudge
from .questions import QuestionWriter
from .service import AuthService, RawFacts
from .store import AuthStore


def build_auth(
    config: Config,
    model,
    directory: Path,
    safety: SafetyService,
    life: LifeService | None,
    reminders: ReminderStore | None,
    spend=None,
) -> AuthService:
    tz = ZoneInfo(config.reminders_tz)
    sources: list[RawFacts] = []
    if reminders is not None:
        def reminder_facts(now: datetime):
            rows = reminders.list_pending()
            return [(f"rem:{r.id}", f"Asked to be reminded on {r.fire_at.astimezone(tz):%A}: {r.text}", "reminder", r.created_at)
                    for r in rows]

        sources.append(reminder_facts)
    if life is not None:
        def plan_facts(now: datetime):
            return [(f"plan:{p.id}", f"Plan{f' on {p.when_date:%A %B %d}' if p.when_date else ''}: {p.text}", "plan", p.created_at)
                    for p in life.store.plans(("upcoming", "asked", "done"))]

        sources.append(plan_facts)
    tools = config.auth_tools.strip().lower()
    protected: tuple[str, ...] | None = None if not tools else (() if tools == "none" else tuple(
        t.strip() for t in config.auth_tools.split(",") if t.strip()))
    return AuthService(
        AuthStore(directory),
        QuestionWriter(model, spend=spend),
        AnswerJudge(model, spend=spend),
        safety,
        tz=tz,
        names=(lambda: life.names()) if life is not None else (lambda: []),
        extra_facts=sources,
        default_enabled=config.auth_enabled,
        mode_questions=config.auth_mode_questions,
        action_need=config.auth_action_need,
        protected=protected,
    )
