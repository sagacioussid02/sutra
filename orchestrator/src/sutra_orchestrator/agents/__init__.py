"""Ephemeral research agents: bounded, sandboxed, read-only.

A run gets a brief and an allowlist of tools, never the conversation or
memory, and returns untrusted findings. See ``openspec/changes/ephemeral-agents/``.
"""

from .commands import AgentCommands
from .db import AgentSchemaError
from .sandbox import DELEGATE_TOOL, Sandbox
from .service import AgentService
from .store import AgentStore, RunRow
from .types import Budget, Findings, ResearchModel, Source, StepResult
from .worker import ResearchWorker

__all__ = [
    "AgentCommands",
    "AgentSchemaError",
    "AgentService",
    "AgentStore",
    "Budget",
    "DELEGATE_TOOL",
    "Findings",
    "ResearchModel",
    "ResearchWorker",
    "RunRow",
    "Sandbox",
    "Source",
    "StepResult",
]
