"""``python -m sutra_orchestrator``: talk to the Sutra gateway in text."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from .classifier import IntentClassifier
from .config import load_config
from .errors import OrchestratorError
from .gateway import McpGatewaySession
from .memstore import SqliteMemory
from .memstore.commands import MemoryCommands
from .model import AnthropicModel
from .orchestrator import Orchestrator
from .repl import configure_logging, run_repl


def _memory_dir(configured: str) -> Path:
    """Relative locations are resolved against the orchestrator directory, not the cwd."""
    path = Path(configured).expanduser()
    return path if path.is_absolute() else Path(__file__).resolve().parents[2] / path


async def _run(verbose: bool) -> int:
    config = load_config()
    configure_logging(verbose, [config.token, config.api_key])

    gateway = McpGatewaySession(
        config.gateway_url, config.token, max_result_bytes=config.max_result_bytes
    )
    await gateway.connect()
    try:
        model = AnthropicModel(
            config.api_key,
            config.model,
            config.classifier_model,
            extractor_model=config.extractor_model,
        )
        memory: SqliteMemory | None = None
        commands: MemoryCommands | None = None
        if config.memory_enabled:
            memory = SqliteMemory(
                _memory_dir(config.memory_dir),
                extractor=model,
                record_replies=config.record_replies,
                hot_days=config.episode_hot_days,
                on_notice=lambda notice: print(f"  {notice}"),
            )
            commands = MemoryCommands(memory)
        orchestrator = Orchestrator(
            model=model,
            gateway=gateway,
            classifier=IntentClassifier(model, timeout=config.classifier_timeout),
            memory=memory,
            max_tool_calls=config.max_tool_calls,
            history_turns=config.history_turns,
            reask_limit=config.reask_limit,
        )
        count = await orchestrator.start()
        print(f"Connected to the gateway. {count} tools available. Blank line to quit.")
        if memory is not None:
            known = sum(1 for m in memory.list_memories() if m.status == "active")
            print(f"Memory is on ({known} remembered). Type /help for memory commands.")
        else:
            print("Memory is off.")
        try:
            await run_repl(orchestrator, commands=commands)
        finally:
            await orchestrator.flush()
            if memory is not None:
                memory.close()
    finally:
        await gateway.close()
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(prog="sutra_orchestrator", description=__doc__)
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="log tool names, outcomes, and per-call timings (never secrets)",
    )
    args = parser.parse_args()
    try:
        sys.exit(asyncio.run(_run(args.verbose)))
    except OrchestratorError as exc:
        print(f"sutra_orchestrator: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
