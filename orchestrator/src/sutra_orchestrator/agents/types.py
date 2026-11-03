"""Plain data types for ephemeral research agents."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class Budget:
    """Hard limits, enforced by code. The model is never relied on to stop itself."""

    max_searches: int = 5
    max_tool_calls: int = 5
    max_turns: int = 6
    run_tokens: int = 8000  # output tokens, summed over a run
    timeout_s: float = 180.0
    daily_runs: int = 3
    daily_tokens: int = 60_000


@dataclass(frozen=True)
class Source:
    url: str
    title: str = ""


@dataclass
class Findings:
    text: str = ""
    sources: list[Source] = field(default_factory=list)
    partial: bool = False
    reason: str = ""  # why a partial run stopped: "time", "tokens", "searches", "turns", "tools"
    searches: int = 0
    tool_calls: int = 0
    output_tokens: int = 0
    turns: int = 0


@dataclass
class StepResult:
    """One request to the research model."""

    content: list[dict[str, Any]]
    stop_reason: str | None = None
    output_tokens: int = 0
    searches: int = 0


class ResearchModel(Protocol):
    async def research_step(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        max_searches: int,
        max_tokens: int,
    ) -> StepResult: ...
