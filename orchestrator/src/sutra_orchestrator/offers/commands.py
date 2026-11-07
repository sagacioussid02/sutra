"""REPL commands for offers: see what was offered and why, and control it."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import timedelta

from typing import TYPE_CHECKING

from .service import KINDS, OffersService

if TYPE_CHECKING:
    from ..events import EventsService

HELP = [
    "Offer commands:",
    "  /offers                    recent offers with outcome and why, the learned bars, blocks",
    "  /offers off | on           stop or resume all unprompted offers",
    "  /offers reset              return the learned bars to where they started",
    "  /offers block <topic|kind> stop offers about a topic, or a kind (followup, timely, nudge)",
    "  /offers unblock <id>       lift a block",
    "  /offers signal <kind> <minutes> <text>   (for testing) hand me an outside signal that expires in N minutes",
    "  /offers forget all         delete all offer history, bars and blocks",
]


class OffersCommands:
    def __init__(self, service: OffersService, events: EventsService | None = None) -> None:
        self._service = service
        self._store = service.store
        self._events = events

    async def handle(self, line: str, read: Callable[[str], Awaitable[str]]) -> list[str] | None:
        line = line.strip()
        if not line.startswith("/"):
            return None
        command, _, rest = line[1:].partition(" ")
        if command.lower() != "offers":
            return None
        sub, _, arg = rest.strip().partition(" ")
        sub, arg = sub.lower(), arg.strip()
        if sub == "":
            return self._overview()
        if sub in ("off", "on"):
            self._service.set_enabled(sub == "on")
            return [f"Unprompted offers are {sub}."]
        if sub == "reset":
            self._service.bars.reset()
            return ["Bars are back where they started. Blocks were kept."]
        if sub == "block":
            if not arg:
                return ["Usage: /offers block <topic|followup|timely|nudge>"]
            kind = arg.lower() if arg.lower() in KINDS else ""
            self._store.add_block(kind, "" if kind else arg, self._service._now())
            return [f"Blocked: {arg}"]
        if sub == "unblock":
            ident = arg.lstrip("#")
            if not ident.isdigit():
                return ["Usage: /offers unblock <id>"]
            return ["Unblocked."] if self._store.remove_block(int(ident)) else ["No such block."]
        if sub == "signal":
            return self._signal(arg)
        if sub == "forget" and arg.lower() == "all":
            self._store.forget_all()
            return ["Deleted offer history, bars, blocks and signals."]
        return HELP

    def _overview(self) -> list[str]:
        now = self._service._now()
        lines = [f"Offers are {'on' if self._service.enabled else 'off'}."]
        for kind in ("followup", "timely"):
            lines.append(
                f"  bar for {kind}: {self._service.bars.value(kind, now):.2f} "
                f"(starts at {self._service.bars.start(kind):.2f})"
            )
        for b in self._store.blocks():
            lines.append(f"  block #{b.id}: {b.topic or b.kind or 'all'}" + (f" [{b.kind}]" if b.topic and b.kind else ""))
        rows = self._store.recent(12)
        if not rows:
            lines.append("  No offers yet.")
        for r in rows:
            lines.append(
                f"  #{r.id} {r.created_at:%m-%d %H:%M} {r.kind}/{r.style} [{r.outcome}] {r.topic}: "
                f"benefit {r.benefit:.2f} vs bar {r.bar:.2f}. {r.reason}"
            )
        return lines

    def _signal(self, arg: str) -> list[str]:
        parts = arg.split(None, 2)
        if len(parts) < 3 or not parts[1].isdigit():
            return ["Usage: /offers signal <kind> <minutes> <text>"]
        kind, minutes, text = parts[0], int(parts[1]), parts[2]
        now = self._service._now()
        if self._events is not None and self._events.enabled and self._events_signal(kind, minutes, text, now):
            return ["Signal sent into the event log as source 'manual'; it will be picked up shortly."]
        sid = self._service.add_signal(
            kind, text, source="manual", expires_at=now + timedelta(minutes=max(1, minutes)), topic_hint=text[:60]
        )
        return [f"Signal #{sid} received."] if sid else ["That signal was empty."]

    def _events_signal(self, kind: str, minutes: int, text: str, now) -> bool:
        """The development shim: put the signal into the event log as an envelope from source 'manual'."""
        from ..events import EventError, event_kind_for  # local: events depends on offers

        event_kind = event_kind_for(kind)
        if event_kind is None:
            return False
        from ..events.kinds import KINDS

        minutes = min(max(1, minutes), KINDS[event_kind]["default_expiry_minutes"])
        envelope = {
            "id": f"manual-{int(now.timestamp() * 1000)}", "source": "manual", "kind": event_kind,
            "user_id": "owner", "received_at": now.isoformat(),
            "expires_at": (now + timedelta(minutes=minutes)).isoformat(),
            "payload": {"summary": text[:200]},
        }
        try:
            return self._events.ingest(envelope) or True
        except EventError:
            return False
