"""Build the research service from configuration."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from zoneinfo import ZoneInfo

from ..config import Config
from ..gateway import GatewaySession, ToolDef
from .sandbox import Sandbox
from .service import AgentService
from .store import AgentStore
from .types import Budget, ResearchModel
from .worker import ResearchWorker


def build_budget(config: Config) -> Budget:
    return Budget(
        max_searches=config.agent_max_searches,
        max_tool_calls=config.agent_max_tool_calls,
        run_tokens=config.agent_run_tokens,
        timeout_s=float(config.agent_timeout_s),
        daily_runs=config.agent_daily_runs,
        daily_tokens=config.agent_daily_tokens,
    )


def build_agent_service(
    config: Config,
    model: ResearchModel,
    gateway: GatewaySession,
    gateway_tools: Callable[[], dict[str, ToolDef]],
    directory: Path,
    tz: ZoneInfo,
) -> AgentService:
    budget = build_budget(config)
    sandbox = Sandbox(gateway, gateway_tools, config.agent_tools)
    return AgentService(AgentStore(directory), ResearchWorker(model, sandbox, budget), budget, tz)
