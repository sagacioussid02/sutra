"""Build idle research from configuration (shared by the text and voice clients)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from ..agents import AgentService
from ..agents.types import Budget
from ..config import Config
from ..graph import GraphService
from ..interests import InterestService
from ..offers import OffersService
from .service import IdleResearcher
from .store import IdleStore


def build_idle(
    config: Config,
    model,
    directory: Path,
    *,
    interests: InterestService | None,
    graph: GraphService | None,
    agents: AgentService | None,
    offers: OffersService | None,
    last_activity: Callable[[], datetime],
    busy: Callable[[], bool],
) -> IdleResearcher | None:
    """None when the feature is not available (its pieces are off). It is still off until switched on."""
    if interests is None or agents is None or offers is None:
        return None
    # A smaller budget than a requested run: the worker takes the tighter of each limit.
    budget = Budget(
        max_searches=config.idle_max_searches,
        max_tool_calls=0,
        run_tokens=config.idle_run_tokens,
        timeout_s=90.0,
    )
    return IdleResearcher(
        IdleStore(directory),
        interests=interests,
        graph=graph,
        agents=agents,
        offers=offers,
        model=model,
        tz=ZoneInfo(config.reminders_tz),
        last_activity=last_activity,
        busy=busy,
        budget=budget,
        daily_runs=config.idle_daily_runs,
        min_hours=float(config.idle_min_hours),
        default_enabled=config.idle_enabled,
        home_area=config.home_area,
    )
