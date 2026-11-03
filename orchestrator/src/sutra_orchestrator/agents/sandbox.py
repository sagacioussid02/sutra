"""What a research run may touch: a fail-closed tool allowlist.

A run gets the web search tool (when enabled) and the gateway tools the user
named in ``SUTRA_AGENT_TOOLS``, and nothing else. Local tools (memory,
reminders, delegation) and ``gateway_confirm`` are never offered, and every
call is checked against the list again when it executes, so a tool name the
model invents is refused, not run.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any, Protocol

from ..gateway import CONFIRM_TOOL, ToolDef, ToolResult

log = logging.getLogger("sutra_orchestrator")

DELEGATE_TOOL = "delegate_research"
MAX_RESULT_CHARS = 8000

REFUSED = "That tool isn't available here."
NEEDS_APPROVAL = "That needs the user's approval, so it can't be used in a research run."


class _Gateway(Protocol):
    async def call_tool(self, name: str, arguments: dict[str, Any]) -> ToolResult: ...


class Sandbox:
    def __init__(
        self,
        gateway: _Gateway,
        available: Callable[[], dict[str, ToolDef]],
        allowed: tuple[str, ...],
        *,
        web_search: bool = True,
    ) -> None:
        self._gateway = gateway
        reserved = {CONFIRM_TOOL, DELEGATE_TOOL}
        for name in allowed:
            if name in reserved:
                log.warning("agent tool allowlist: %r is never available to a run; ignored", name)
        self._available = available  # read late: gateway tools are fetched after startup
        self._allowed = tuple(n for n in allowed if n not in reserved)
        self.web_search = web_search

    @property
    def _tools(self) -> dict[str, ToolDef]:
        available = self._available()
        return {name: available[name] for name in self._allowed if name in available}

    def tool_defs(self) -> list[dict[str, Any]]:
        return [
            {"name": t.name, "description": t.description, "input_schema": t.input_schema}
            for t in self._tools.values()
        ]

    async def call(self, name: str, args: dict[str, Any]) -> tuple[str, bool]:
        """Run one allowlisted gateway tool. Returns (content, is_error)."""
        if name not in self._tools:
            log.warning("research run requested unavailable tool %r; refused", name)
            return REFUSED, True
        result = await self._gateway.call_tool(name, args if isinstance(args, dict) else {})
        if result.kind == "pending":
            # Never confirmed: the user's yes is the only thing that can release a held action.
            return NEEDS_APPROVAL, True
        if result.kind == "error":
            return "The tool failed.", True
        return result.text[:MAX_RESULT_CHARS], False
