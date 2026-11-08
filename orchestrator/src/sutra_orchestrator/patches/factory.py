"""Build the patch service from configuration."""

from __future__ import annotations

import shlex
from pathlib import Path
from zoneinfo import ZoneInfo

from ..agents.types import Budget, ResearchModel
from ..config import Config
from . import tester
from .drafter import Drafter
from .service import PatchService
from .store import PatchStore
from .workspace import Workspace

DEFAULT_TEST_COMMAND = "python -m pytest -x -q"


def build_budget(config: Config) -> Budget:
    return Budget(
        max_searches=0,
        max_tool_calls=config.patches_max_tool_calls,
        max_turns=config.patches_max_tool_calls + 2,
        run_tokens=config.patches_run_tokens,
        timeout_s=float(config.patches_timeout_s),
        daily_runs=config.patches_daily_runs,
        daily_tokens=config.patches_daily_tokens,
    )


def build_patch_service(
    config: Config, model: ResearchModel, repo: Path, directory: Path, tz: ZoneInfo
) -> PatchService:
    budget = build_budget(config)
    command = shlex.split(config.patches_test_command or DEFAULT_TEST_COMMAND)
    test_dir = config.patches_test_dir
    test_timeout = float(config.patches_test_timeout_s)

    async def run_tests(ws: Workspace) -> tester.TestOutcome:
        return await tester.run_tests(ws.root, command, ws.root / test_dir, test_timeout)

    return PatchService(
        PatchStore(directory), Drafter(model, run_tests, budget), repo, directory / "worktrees", budget, tz
    )
