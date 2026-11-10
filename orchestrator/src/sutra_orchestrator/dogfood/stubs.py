"""Stand-ins at the adapter boundary: a recording gateway and the run's model.

The gateway is where Sutra's actions leave the process, so it is the one
seam where simulation can be total without being fake. Everything between
``Orchestrator.respond`` and this boundary is production code. Read-only
tools answer from synthetic fixtures; mutating tools answer the way the
real gateway answers a confirm-first tool (a pending action) and are
recorded; ``gateway_confirm`` is recorded as an execution and executes
nothing.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable

from ..gateway import CONFIRM_TOOL, PendingInfo, ToolDef, ToolResult
from ..model import ModelResponse

READ_ONLY_TOOLS = {
    "notes_search": {"notes": [{"title": "Packing list", "body": "passport, charger, umbrella"}]},
    "calendar_list_events": {"events": [{"title": "Dentist", "start": "2026-11-05T16:00:00Z"}]},
    "weather_forecast": {"forecast": "light rain after 4pm, 9C"},
}
MUTATING_TOOLS = {
    "calendar_add_event": "Add a calendar event",
    "message_send": "Send a message",
    "finanxe_create_goal": "Create a savings goal",
    "smart_home_set": "Change a smart-home device",
}


def _schema() -> dict[str, Any]:
    return {"type": "object", "properties": {}, "additionalProperties": True}


@dataclass
class Recorded:
    name: str
    arguments: dict[str, Any]
    outcome: str  # "read" | "pending" | "executed" | "unknown"


@dataclass
class RecordingGateway:
    """A GatewaySession whose mutating tools are recorded, never run."""

    now: Callable[[], datetime]
    calls: list[Recorded] = field(default_factory=list)
    pending: dict[str, str] = field(default_factory=dict)  # pending id -> tool name
    _next: int = 0

    async def list_tools(self) -> list[ToolDef]:
        tools = [ToolDef(n, f"(sandbox) read {n.replace('_', ' ')}", _schema()) for n in READ_ONLY_TOOLS]
        tools += [ToolDef(n, f"(sandbox) {d}; needs the user's confirmation", _schema()) for n, d in MUTATING_TOOLS.items()]
        tools.append(ToolDef(CONFIRM_TOOL, "confirm a pending action", _schema()))
        return tools

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        if name in READ_ONLY_TOOLS:
            self.calls.append(Recorded(name, dict(arguments), "read"))
            return ToolResult(kind="ok", text=json.dumps(READ_ONLY_TOOLS[name]))
        if name in MUTATING_TOOLS:
            self._next += 1
            pid = f"sandbox-{self._next}"
            self.pending[pid] = name
            self.calls.append(Recorded(name, dict(arguments), "pending"))
            return ToolResult(
                kind="pending",
                text="{}",
                pending=PendingInfo(
                    pending_id=pid,
                    description=f"{MUTATING_TOOLS[name]}: {json.dumps(arguments, sort_keys=True)}",
                    expires_at=self.now() + timedelta(minutes=5),
                ),
            )
        if name == CONFIRM_TOOL:
            pid = str(arguments.get("pending_id", ""))
            self.calls.append(Recorded(name, dict(arguments), "executed"))
            return ToolResult(kind="ok", text=json.dumps({"status": "done", "simulated": True, "tool": self.pending.get(pid)}))
        self.calls.append(Recorded(name, dict(arguments), "unknown"))
        return ToolResult(kind="error", text=f"no sandbox tool named {name}", category="other")

    async def close(self) -> None:
        return None

    @property
    def executed(self) -> list[Recorded]:
        return [c for c in self.calls if c.outcome == "executed"]


class BudgetExceeded(RuntimeError):
    """The run spent its configured model-call budget."""


class ScriptedModel:
    """A free, deterministic stand-in for the model.

    It answers every turn with a fixed short reply and never asks for a
    tool, and it labels every confirmation reply the fast path did not
    settle as ``unclear``. So in scripted mode the batteries exercise the
    code paths that need no model (reminder parsing and firing, the
    confirmation fast path and gate, the offers arbiter) at no cost;
    scenarios marked ``requires_live`` are skipped.
    """

    reply = "Okay."

    async def complete(self, *, system, messages, tools, allow_tools=True, on_text=None) -> ModelResponse:
        return ModelResponse(content=[{"type": "text", "text": self.reply}])

    async def classify(self, *, system: str, user: str) -> str:
        return "unclear"

    async def structured(self, *, name: str, system: str, user: str) -> dict[str, Any]:
        return {}

    async def extract(self, *, system: str, user: str) -> list[dict[str, Any]]:
        return []

    async def reflect_interests(self, *, system: str, user: str) -> list[dict[str, Any]]:
        return []


class BudgetedModel:
    """Counts every model call a run makes and stops the run at its budget."""

    _COUNTED = ("complete", "classify", "structured", "extract", "reflect_interests")

    def __init__(self, inner: Any, budget: int) -> None:
        self._inner = inner
        self.budget = budget
        self.calls = 0
        self.refused = 0  # calls refused for want of budget; a scenario that hit one is not graded

    def __getattr__(self, name: str) -> Any:
        attr = getattr(self._inner, name)
        if name not in self._COUNTED:
            return attr

        async def counted(*args: Any, **kwargs: Any) -> Any:
            if self.calls >= self.budget:
                self.refused += 1
                raise BudgetExceeded(f"model-call budget of {self.budget} spent")
            self.calls += 1
            return await attr(*args, **kwargs)

        return counted
