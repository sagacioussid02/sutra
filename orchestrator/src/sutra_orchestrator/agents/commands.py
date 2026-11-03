"""REPL commands for research runs."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from .service import AgentService

HELP = [
    "Research commands:",
    "  /agents          recent research runs and today's usage",
    "  /agents purge    delete the record of all runs",
]


class AgentCommands:
    def __init__(self, service: AgentService) -> None:
        self._service = service

    async def handle(self, line: str, read: Callable[[str], Awaitable[str]]) -> list[str] | None:
        line = line.strip()
        if not line.startswith("/"):
            return None
        command, _, rest = line[1:].partition(" ")
        if command.lower() != "agents":
            return None
        rest = rest.strip()
        if rest == "purge":
            return [f"Deleted {self._service.store.purge()} run(s)."]
        if rest:
            return ["Usage: /agents   or   /agents purge"]
        budget = self._service.budget
        runs, tokens = self._service.today_usage()
        lines = [f"Today: {runs} of {budget.daily_runs} runs, {tokens} of {budget.daily_tokens} tokens."]
        rows = self._service.store.list_runs(10)
        if not rows:
            return lines + ["No research runs yet."]
        for r in rows:
            note = f" ({r.reason})" if r.reason else ""
            lines.append(
                f"#{r.id} {r.status}{note}, {r.searches} searches, {r.output_tokens} tokens: {r.task}"
            )
        return lines
