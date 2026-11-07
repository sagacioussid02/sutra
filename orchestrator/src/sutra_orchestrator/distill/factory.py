"""Build the distillation service from configuration (shared by the text and voice clients)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from ..config import Config
from ..memstore import SqliteMemory
from ..model import StructuredModel
from ..offers import OffersService
from .service import DistillService, PassResult

SOURCE = "memory-distill"


def build_distill(
    config: Config,
    model: StructuredModel,
    memory,
    offers: OffersService | None,
    *,
    last_activity: Callable[[], datetime] | None = None,
    busy: Callable[[], bool] | None = None,
) -> DistillService | None:
    if not config.distill_enabled or not isinstance(memory, SqliteMemory):
        return None
    holder: dict[str, DistillService] = {}

    def digest(result: PassResult) -> None:
        """One notice per productive pass: how many are waiting, what you owe first. Never per item."""
        if offers is None or not offers.enabled:
            return
        owe = f", including {result.commitments} you owe or are waiting on" if result.commitments else ""
        teaser = f"I picked up {result.created} things from our chats worth keeping{owe}. Have a look with /proposals when you can."
        svc = holder["svc"]
        offers.add_ready_signal(
            "distill", teaser, teaser, source=SOURCE, topic_hint="distill-digest", expires_at=svc._now() + _DIGEST_LIFE
        )

    svc = DistillService(
        memory, model, hours=config.distill_hours, daily_calls=config.distill_calls,
        exclude_tool_prefixes=config.reflection_exclude_tools, last_activity=last_activity, busy=busy, digest=digest,
    )
    holder["svc"] = svc
    return svc


from datetime import timedelta  # noqa: E402

_DIGEST_LIFE = timedelta(days=3)
