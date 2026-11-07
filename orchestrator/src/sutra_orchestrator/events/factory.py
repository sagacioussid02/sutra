"""Build the event service, its listener and the offers consumer from configuration."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from ..config import Config
from ..offers import OffersService
from .consumers import OFFERS_CONSUMER, kinds_for_offers, offers_consumer
from .server import EventListener
from .service import EventsService
from .store import EventStore


def build_events(
    config: Config, offers: OffersService | None, resolve_dir: Callable[[str], Path]
) -> tuple[EventsService, EventListener] | None:
    if not config.events_enabled:
        return None
    service = EventsService(
        EventStore(resolve_dir(config.events_dir)),
        secret=config.events_secret,
        cap=config.events_cap,
        retention_days=config.events_retention_days,
        max_attempts=config.events_max_attempts,
    )
    if offers is not None:
        service.register(OFFERS_CONSUMER, kinds_for_offers(), offers_consumer(offers))
    return service, EventListener(service, config.events_port)
