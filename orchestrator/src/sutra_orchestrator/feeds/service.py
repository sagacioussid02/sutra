"""Curiosity feeds: weather alerts, topic news, and a morning brief, all opt-in.

Each producer files signals for the offers system, which judges them against what the user has said and
planned, asks first when the content came from the web, and learns from how they are received. Nothing here
speaks to the user or acts on anything. Only a city name (weather) or a topic word (news) ever leaves.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from ..interests import InterestService
from ..memory import LocalTool, ToolContext
from ..offers import OffersService
from . import news as news_mod
from . import weather as weather_mod
from .http import Fetch, fetch_text

log = logging.getLogger("sutra_orchestrator")

WEATHER_SOURCE = "open-meteo"
NEWS_SOURCE = "news-feed"
BRIEF_TOOL = "morning_brief"
NEWS_BAR_CEILING = 0.8
NEWS_TOPIC_GAP = timedelta(hours=20)
POLL_SECONDS = 1800.0

BriefSource = Callable[[datetime], list[str]]


class FeedService:
    def __init__(
        self,
        offers: OffersService,
        interests: InterestService | None,
        *,
        area: str = "",
        news_on: bool = False,
        news_topics: tuple[str, ...] = (),
        imperial: bool = True,
        tz: ZoneInfo,
        fetch: Fetch | None = None,
        brief_sources: list[BriefSource] | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._offers = offers
        self._interests = interests
        self._area = area.strip()
        self._news_default = news_on
        self._news_topics = tuple(t for t in news_topics if t.strip())
        self._imperial = imperial
        self._tz = tz
        self._fetch = fetch or fetch_text
        self._sources = brief_sources or []
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._task: asyncio.Task[None] | None = None
        self._store = offers.store  # small key-value state lives with the offers

    # ---------------------------------------------------------------- settings

    @property
    def area(self) -> str:
        return self._area

    @property
    def news_enabled(self) -> bool:
        stored = self._store.get_meta("feeds:news")
        return self._news_default if stored is None else stored == "1"

    def set_news(self, on: bool) -> None:
        self._store.set_meta("feeds:news", "1" if on else "0")

    def last(self, feed: str) -> datetime | None:
        raw = self._store.get_meta(f"feeds:last:{feed}")
        return datetime.fromisoformat(raw) if raw else None

    def _stamp(self, feed: str) -> None:
        self._store.set_meta(f"feeds:last:{feed}", self._now().isoformat())

    # ----------------------------------------------------------------- weather

    async def _coords(self) -> tuple[float, float, str] | None:
        raw = self._store.get_meta("feeds:coords")
        if raw:
            try:
                data = json.loads(raw)
                if data.get("area") == self._area:
                    return data["lat"], data["lon"], data["name"]
            except (ValueError, KeyError):
                pass
        found = await weather_mod.locate(self._area, self._fetch)
        if found is not None:
            self._store.set_meta("feeds:coords", json.dumps({"area": self._area, "lat": found[0], "lon": found[1], "name": found[2]}))
        return found

    async def _forecast(self):
        coords = await self._coords() if self._area else None
        if coords is None:
            return None, ""
        data = await weather_mod.forecast(coords[0], coords[1], self._fetch)
        return data, coords[2]

    async def poll_weather(self) -> int:
        """File a signal for each notable condition not yet filed today. Returns how many."""
        if not self._area or not self._offers.enabled:
            return 0
        data, name = await self._forecast()
        self._stamp("weather")
        if data is None:
            return 0
        now = self._now()
        today = now.astimezone(self._tz).date().isoformat()
        filed = 0
        for item in weather_mod.notable(data, now, imperial=self._imperial):
            key = f"feeds:wx:{item.kind}:{today}"
            if self._store.get_meta(key):
                continue
            sid = self._offers.add_signal(
                "weather", item.summary, source=WEATHER_SOURCE, urgency="medium",
                expires_at=item.ends + timedelta(hours=1), topic_hint=f"{item.kind} near {name}",
            )
            if sid is not None:
                self._store.set_meta(key, "1")
                filed += 1
        return filed

    # -------------------------------------------------------------------- news

    def _topics(self) -> list[str]:
        topics = list(self._news_topics)
        if self._interests is not None:
            topics += [r.topic for r in self._interests.store.list(("active",))]
        out: list[str] = []
        for t in topics:
            if t and t.lower() not in {o.lower() for o in out} and not self._offers.arbiter.is_blocked("timely", t):
                out.append(t)
        return out

    async def poll_news(self) -> int:
        """At most one roundup a day, on the topic fetched longest ago, while the news bar allows it."""
        if not self.news_enabled or not self._offers.enabled:
            return 0
        now = self._now()
        today = now.astimezone(self._tz).date().isoformat()
        if self._store.get_meta("feeds:news_day") == today:
            return 0
        if self._offers.bars.value("news", now) >= NEWS_BAR_CEILING:
            return 0

        def fetched(topic: str) -> datetime | None:
            raw = self._store.get_meta(f"feeds:news:{topic.lower()}")
            return datetime.fromisoformat(raw) if raw else None

        candidates = [t for t in self._topics() if fetched(t) is None or now - fetched(t) >= NEWS_TOPIC_GAP]  # type: ignore[operator]
        candidates.sort(key=lambda t: fetched(t) or datetime.min.replace(tzinfo=timezone.utc))
        for topic in candidates[:3]:
            self._store.set_meta(f"feeds:news:{topic.lower()}", now.isoformat())
            items = await news_mod.headlines(topic, self._fetch)
            self._stamp("news")
            if not items:
                continue
            sid = self._offers.add_signal(
                "news", news_mod.summary(topic, items), source=NEWS_SOURCE, urgency="low",
                expires_at=now + timedelta(days=1), topic_hint=topic,
            )
            if sid is not None:
                self._store.set_meta("feeds:news_day", today)
                return 1
        return 0

    async def poll(self) -> None:
        """One pass over the feeds that are on. Never raises."""
        for step in (self.poll_weather, self.poll_news):
            try:
                await step()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.debug("feed poll failed (%s)", type(exc).__name__)

    # ------------------------------------------------------------ morning brief

    async def brief(self) -> str:
        """Plain lines for today, for the model to say naturally. Read-only."""
        now = self._now()
        lines: list[str] = []
        for source in self._sources:
            try:
                lines += source(now)
            except Exception:
                log.debug("a brief source failed", exc_info=True)
        if self._area:
            data, name = await self._forecast()
            lines.append(f"Weather in {name}: " + (weather_mod.outlook(data, now, imperial=self._imperial) if data else "not available right now."))
        waiting = [s for s in self._offers.store.signals(("ready",)) if s.kind == "research" and s.expires_at > now]
        if waiting:
            lines.append("A research finding is waiting; offer it if they want it.")
        return "\n".join(lines) if lines else "Nothing is scheduled for today, and there is nothing waiting."

    def tools(self) -> list[LocalTool]:
        async def handler(args: dict, context: ToolContext) -> str:
            return await self.brief()

        return [
            LocalTool(
                name=BRIEF_TOOL,
                description=(
                    "Get what is on for the user today (reminders, plans, the weather, anything waiting), when they "
                    "ask for a morning brief or what their day looks like. Read-only. Say it naturally and briefly."
                ),
                input_schema={"type": "object", "properties": {}},
                handler=handler,
            )
        ]

    # --------------------------------------------------------------- background

    def start_task(self, interval: float = POLL_SECONDS) -> asyncio.Task[None]:
        async def loop() -> None:
            while True:
                await self.poll()
                await asyncio.sleep(interval)

        if self._task is None:
            self._task = asyncio.create_task(loop(), name="sutra-feeds")
        return self._task

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
