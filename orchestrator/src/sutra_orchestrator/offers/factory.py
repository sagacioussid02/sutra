"""Build the graph and offers services from configuration (shared by the text and voice clients)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from zoneinfo import ZoneInfo

from ..config import Config
from ..graph import GraphService, GraphStore
from ..model import StructuredModel
from .judge import Judge
from .service import OffersService
from .store import OffersStore


def build_graph_and_offers(
    config: Config,
    model: StructuredModel,
    resolve_dir: Callable[[str], Path],
) -> tuple[GraphService | None, OffersService | None]:
    tz = ZoneInfo(config.reminders_tz)
    offers: OffersService | None = None
    if config.offers_enabled:
        offers = OffersService(
            OffersStore(resolve_dir(config.offers_dir)),
            tz,
            daily_max=config.offers_daily_max,
            calls_per_day=config.offers_calls_per_day,
            urgent_sources=config.offers_urgent_sources,
        )
    graph: GraphService | None = None
    if config.graph_enabled:
        graph = GraphService(
            GraphStore(resolve_dir(config.graph_dir)),
            model,
            exclude_tool_prefixes=config.reflection_exclude_tools,
            spend=offers.spend_call if offers is not None else None,
        )
    if offers is not None:
        offers.attach(graph, Judge(model, spend=offers.spend_call))
    return graph, offers
