"""The /distill command: run a pass now, see where it is, switch it off."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from .service import DistillService, PassResult

HELP = [
    "Distill commands:",
    "  /distill                 where the last pass got to",
    "  /distill run             look through recent conversations now",
    "  /distill backfill        one-time pass starting from the oldest recent conversations",
    "  /distill off | on        stop or resume the scheduled pass",
]


def _summary(r: PassResult) -> list[str]:
    if r.skipped and not r.created:
        return [f"Nothing proposed: {r.skipped}."]
    extra = f", {r.commitments} of them something you owe or are waiting on" if r.commitments else ""
    return [f"Read {r.read} conversations and proposed {r.created} things{extra}. Review them with /proposals."]


class DistillCommands:
    def __init__(self, service: DistillService) -> None:
        self._service = service

    async def handle(self, line: str, read: Callable[[str], Awaitable[str]]) -> list[str] | None:
        line = line.strip()
        if not line.startswith("/"):
            return None
        command, _, rest = line[1:].partition(" ")
        if command.lower() != "distill":
            return None
        sub = rest.strip().lower()
        if sub in ("off", "on"):
            self._service.enabled = sub == "on"
            return [f"Distillation is {sub}."]
        if sub == "run":
            return _summary(await self._service.run_pass())
        if sub == "backfill":
            return _summary(await self._service.run_pass(backfill=True))
        if sub:
            return HELP
        return self._service.status()
