"""REPL commands for the episode graph."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime, timezone

from .service import GraphService
from .store import Node

HELP = [
    "Graph commands:",
    "  /graph                 list conversations I remember, newest first",
    "  /graph <id>            one conversation, and how it links to others and why",
    "  /graph forget <id>     delete one conversation",
    "  /graph forget all      delete everything",
]


def _line(n: Node, now: datetime) -> str:
    opened = f" (open: {', '.join(n.open)})" if n.open else ""
    return f"#{n.id} [{n.status}] {n.topic}{opened}  last {n.last_touched:%Y-%m-%d}"


class GraphCommands:
    def __init__(self, service: GraphService) -> None:
        self._service = service
        self._store = service.store

    async def handle(self, line: str, read: Callable[[str], Awaitable[str]]) -> list[str] | None:
        line = line.strip()
        if not line.startswith("/"):
            return None
        command, _, rest = line[1:].partition(" ")
        if command.lower() != "graph":
            return None
        sub, _, arg = rest.strip().partition(" ")
        sub, arg = sub.lower(), arg.strip()
        now = datetime.now(timezone.utc)
        if sub == "":
            nodes = self._store.list(include_archived=True)
            return [_line(n, now) for n in nodes] or ["Nothing yet. I build this from our conversations."]
        if sub == "forget":
            if arg.lower() == "all":
                return [f"Deleted {self._store.forget_all()} conversation(s) and their links."]
            ident = arg.lstrip("#")
            if not ident.isdigit():
                return ["Usage: /graph forget <id|all>"]
            return [f"Deleted #{ident}."] if self._store.forget(int(ident)) else ["Nothing deleted."]
        ident = sub.lstrip("#")
        if ident.isdigit():
            node = self._store.get(int(ident))
            if node is None:
                return [f"There is no conversation #{ident}."]
            out = [_line(node, now), f"  {node.gist}"]
            for e in self._store.edges_of(node.id):
                other = self._store.get(e.other(node.id))
                if other is None:
                    continue
                arrow = e.type if e.a == node.id else f"{e.type} (from them)"
                out.append(f"  {arrow} -> #{other.id} {other.topic}: {e.reason}")
            return out
        return HELP
