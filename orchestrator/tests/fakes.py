"""Scripted fakes for the model, the intent model, and the gateway."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Any

from sutra_orchestrator.classifier import IntentClassifier
from sutra_orchestrator.gateway import PendingInfo, ToolDef, ToolResult
from sutra_orchestrator.model import ModelResponse
from sutra_orchestrator.orchestrator import Orchestrator

NOW = datetime(2026, 10, 12, 12, 0, 0, tzinfo=timezone.utc)


def text(s: str) -> dict[str, Any]:
    return {"type": "text", "text": s}


def tool_use(name: str, args: dict[str, Any] | None = None, id: str = "tu_1") -> dict[str, Any]:
    return {"type": "tool_use", "id": id, "name": name, "input": args or {}}


def resp(*blocks: dict[str, Any]) -> ModelResponse:
    return ModelResponse(content=list(blocks))


class FakeModel:
    """Implements both ModelClient and IntentModel.

    ``script`` entries are ModelResponse objects or callables taking the
    request dict and returning one. ``labels`` maps a user reply substring to
    the label the classifier returns (default "unclear").
    """

    def __init__(self, script: list[Any] | None = None, labels: dict[str, str] | None = None):
        self.script = list(script or [])
        self.labels = labels or {}
        self.calls: list[dict[str, Any]] = []
        self.classify_calls: list[dict[str, str]] = []
        self.classify_error: Exception | None = None
        self.classify_delay: float = 0.0
        self.classify_raw: str | None = None

    async def complete(self, *, system, messages, tools, allow_tools=True) -> ModelResponse:
        request = {
            "system": system,
            "messages": json.loads(json.dumps(messages)),
            "tools": tools,
            "allow_tools": allow_tools,
        }
        self.calls.append(request)
        if not self.script:
            raise AssertionError("FakeModel script exhausted")
        item = self.script.pop(0)
        return item(request) if callable(item) else item

    async def classify(self, *, system: str, user: str) -> str:
        self.classify_calls.append({"system": system, "user": user})
        if self.classify_delay:
            await asyncio.sleep(self.classify_delay)
        if self.classify_error is not None:
            raise self.classify_error
        if self.classify_raw is not None:
            return self.classify_raw
        reply = user.split("User's reply:\n", 1)[-1]
        for needle, label in self.labels.items():
            if needle in reply:
                return label
        return "unclear"


class FakeGateway:
    """A GatewaySession whose tool results are scripted per tool name."""

    def __init__(self, tools: list[ToolDef] | None = None, results: dict[str, Any] | None = None):
        self.tools = tools or []
        self.results = results or {}
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.closed = False

    async def list_tools(self) -> list[ToolDef]:
        return self.tools

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        self.calls.append((name, arguments))
        result = self.results.get(name)
        if result is None:
            return ToolResult(kind="error", text=f"no scripted result for {name}", category="other")
        if isinstance(result, list):
            return result.pop(0)
        return result(arguments) if callable(result) else result

    async def close(self) -> None:
        self.closed = True

    def calls_to(self, name: str) -> list[dict[str, Any]]:
        return [a for n, a in self.calls if n == name]


def schema() -> dict[str, Any]:
    return {"type": "object", "properties": {}}


def ok(payload: Any) -> ToolResult:
    return ToolResult(kind="ok", text=json.dumps(payload))


def pending(
    pid: str = "p1",
    description: str = "Create a goal named Vacation for 2000 dollars.",
    expires: datetime | None = None,
) -> ToolResult:
    expires = expires or NOW + timedelta(minutes=5)
    return ToolResult(
        kind="pending",
        text="{}",
        pending=PendingInfo(pending_id=pid, description=description, expires_at=expires),
    )


def default_tools() -> list[ToolDef]:
    names = [
        "finanxe_list_debts",
        "finanxe_get_snapshot",
        "finanxe_create_goal",
        "finanxe_add_calendar_event",
        "gateway_confirm",
    ]
    return [ToolDef(n, f"{n} description", schema()) for n in names]


class Clock:
    def __init__(self, start: datetime = NOW):
        self.t = start

    def __call__(self) -> datetime:
        return self.t

    def advance(self, **kw: Any) -> None:
        self.t += timedelta(**kw)


async def make_orchestrator(
    model: FakeModel,
    gateway: FakeGateway | None = None,
    *,
    memory: Any = None,
    clock: Callable[[], datetime] | None = None,
    classifier_timeout: float = 1.0,
    **kwargs: Any,
) -> tuple[Orchestrator, FakeGateway]:
    gateway = gateway or FakeGateway(tools=default_tools())
    orch = Orchestrator(
        model=model,
        gateway=gateway,
        classifier=IntentClassifier(model, timeout=classifier_timeout),
        memory=memory,
        now=clock or Clock(),
        **kwargs,
    )
    await orch.start()
    return orch, gateway


def assert_valid_history(orch: Orchestrator) -> None:
    """Every tool_use must be answered by a tool_result in the next message."""
    messages = orch._flat_history()
    for i, message in enumerate(messages):
        content = message["content"]
        if isinstance(content, str):
            continue
        ids = [b["id"] for b in content if b.get("type") == "tool_use"]
        if ids:
            nxt = messages[i + 1]["content"]
            answered = {b["tool_use_id"] for b in nxt if b.get("type") == "tool_result"}
            assert set(ids) <= answered, f"unanswered tool_use at message {i}"
    roles = [m["role"] for m in messages]
    assert all(a != b for a, b in zip(roles, roles[1:])), f"roles do not alternate: {roles}"
