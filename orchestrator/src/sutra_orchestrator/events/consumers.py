"""Consumers of the event log. The offers consumer turns events into signals for the ask-first arbiter."""

from __future__ import annotations

from ..offers import OffersService
from .kinds import Event

OFFERS_CONSUMER = "offers"
# Event kind -> the signal kind the offers judge already understands.
SIGNAL_KIND = {
    "weather_warning": "weather",
    "calendar_change": "calendar",
    "camera_motion": "camera",
    "broker_fill": "broker",
    "phone_notification": "notification",
}


def offers_consumer(offers: OffersService):
    """Hand each event to the offers intake. Urgency is only the producer's claim: the offers
    service still requires an allowlisted source for the urgent path. Nothing here can create a
    memory, a confirmation or a tier change: the only call is ``add_signal``."""

    def handle(event: Event) -> None:
        summary = event.payload.get("summary", "")
        urgency = event.payload.get("urgency") or None
        offers.add_signal(
            SIGNAL_KIND.get(event.kind, event.kind), summary, source=event.source, urgency=urgency,
            expires_at=event.expires_at, topic_hint=event.payload.get("ref") or summary[:60],
        )

    return handle


def kinds_for_offers() -> tuple[str, ...]:
    return tuple(SIGNAL_KIND)


def event_kind_for(text: str) -> str | None:
    """The event kind for a signal kind a person typed (``weather`` -> ``weather_warning``)."""
    t = text.lower()
    for kind, signal in SIGNAL_KIND.items():
        if t in (kind, signal):
            return kind
    return None
