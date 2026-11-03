"""Build the feeds from configuration (shared by the text and voice clients)."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from ..config import Config
from ..interests import InterestService
from ..life import LifeService
from ..offers import OffersService
from ..reminders import ReminderStore
from .service import BriefSource, FeedService


def build_feeds(
    config: Config,
    offers: OffersService | None,
    interests: InterestService | None,
    reminders: ReminderStore | None,
    life: LifeService | None,
) -> FeedService | None:
    if offers is None or not config.feeds_enabled:
        return None
    tz = ZoneInfo(config.reminders_tz)
    sources: list[BriefSource] = []
    if reminders is not None:
        def reminder_lines(now: datetime) -> list[str]:
            today = now.astimezone(tz).date()
            return [
                f"Reminder at {r.fire_at.astimezone(tz):%I:%M %p}".replace(" 0", " ").replace("at 0", "at ") + f": {r.text}"
                for r in reminders.list_pending()
                if r.fire_at.astimezone(tz).date() == today
            ]

        sources.append(reminder_lines)
    if life is not None:
        def plan_lines(now: datetime) -> list[str]:
            today = now.astimezone(tz).date()
            out = []
            for p in life.store.plans(("upcoming",)):
                if p.when_date is not None and 0 <= (p.when_date - today).days <= 1:
                    out.append(f"Plan {'today' if p.when_date == today else 'tomorrow'}: {p.text}")
            return out

        sources.append(plan_lines)
    return FeedService(
        offers, interests, area=config.home_area, news_on=config.news_enabled, news_topics=config.news_topics,
        imperial=config.units == "imperial", tz=tz, brief_sources=sources,
    )
