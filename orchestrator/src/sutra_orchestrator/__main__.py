"""``python -m sutra_orchestrator``: talk to the Sutra gateway in text."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

from .classifier import IntentClassifier
from .config import load_config
from .errors import OrchestratorError
from .gateway import McpGatewaySession
from .memstore import SqliteMemory
from .memstore.commands import MemoryCommands
from .model import AnthropicModel
from .orchestrator import Orchestrator
from .agents import AgentCommands
from .interests import InterestCommands, InterestService, InterestStore, Reflector
from .graph import GraphCommands
from .offers import OffersCommands, build_graph_and_offers
from .idle import IdleCommands, build_idle
from .lessons import LessonCommands, build_lessons
from .agents.factory import build_agent_service
from .reminders import ReminderScheduler, ReminderService, ReminderStore
from .reminders.commands import ReminderCommands
from .repl import CommandSet, configure_logging, run_repl


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
            agent_model=config.agent_model,
        )
        memory: SqliteMemory | None = None
        memory_commands: MemoryCommands | None = None
        if config.memory_enabled:
            memory = SqliteMemory(
                _memory_dir(config.memory_dir),
                extractor=model,
                record_replies=config.record_replies,
                hot_days=config.episode_hot_days,
                on_notice=lambda notice: print(f"  {notice}"),
            )
            memory_commands = MemoryCommands(memory)
        reminder_store: ReminderStore | None = None
        reminder_commands: ReminderCommands | None = None
        reminder_scheduler: ReminderScheduler | None = None
        reminders: ReminderService | None = None
        if config.reminders_enabled:
            tz = ZoneInfo(config.reminders_tz)
            reminder_store = ReminderStore(_memory_dir(config.reminders_dir))
            reminders = ReminderService(reminder_store, tz)
            reminder_commands = ReminderCommands(reminder_store, tz=tz)
            reminder_scheduler = ReminderScheduler(
                reminder_store,
                on_deliver=lambda entry: print(f"  reminder: {entry.text}"),
            )
        interests = None
        interest_commands = None
        if config.interests_enabled:
            interest_store = InterestStore(_memory_dir(config.interests_dir))
            reflector = None
            if config.reflection_enabled and memory is not None:
                reflector = Reflector(
                    memory,
                    interest_store,
                    model,
                    window_days=config.reflection_days,
                    exclude_tool_prefixes=config.reflection_exclude_tools,
                )
            interests = InterestService(
                interest_store,
                ZoneInfo(config.reminders_tz),
                reflector=reflector,
                reflection_hours=config.reflection_hours,
                nudge_hours=config.nudge_hours,
            )
            interest_commands = InterestCommands(interests)
        graph, offers = build_graph_and_offers(config, model, _memory_dir)
        graph_commands = GraphCommands(graph) if graph is not None else None
        offers_commands = OffersCommands(offers) if offers is not None else None
        agents = None
        agent_commands = None
        if config.agents_enabled:
            agents = build_agent_service(
                config, model, gateway, lambda: orchestrator.gateway_tools,
                _memory_dir(config.agents_dir), ZoneInfo(config.reminders_tz),
            )
            agent_commands = AgentCommands(agents)
        lessons = (
            build_lessons(config, model, memory, offers, _memory_dir(config.lessons_dir))
            if config.lessons_enabled
            else None
        )
        lesson_commands = LessonCommands(lessons) if lessons is not None else None
        idle = build_idle(
            config, model, _memory_dir(config.idle_dir),
            interests=interests, graph=graph, agents=agents, offers=offers,
            last_activity=lambda: orchestrator.last_activity,
            busy=lambda: orchestrator.pending is not None or bool(orchestrator.research_tasks),
        )
        idle_commands = IdleCommands(idle) if idle is not None else None
        # Reminder commands first: the memory handler answers every "/"
        # line (including "unknown command"), so it must be tried last.
        commands = CommandSet(
            reminder_commands, agent_commands, interest_commands, graph_commands, offers_commands,
            idle_commands, lesson_commands, memory_commands
        )
        orchestrator = Orchestrator(
            model=model,
            gateway=gateway,
            classifier=IntentClassifier(model, timeout=config.classifier_timeout),
            memory=memory,
            reminders=reminders,
            agents=agents,
            interests=interests,
            graph=graph,
            offers=offers,
            lessons=lessons,
            max_tool_calls=config.max_tool_calls,
            history_turns=config.history_turns,
            reask_limit=config.reask_limit,
        )
        if agents is not None:
            def adopt(label: str, task: str, work) -> None:
                def done(t) -> None:
                    if t.cancelled():
                        return
                    try:
                        reply = t.result()
                    except Exception:
                        reply = "The research didn't work out."
                    orchestrator.note_background_result(task, reply)
                    print(f"\nsutra (research: {label})> {reply}")

                work.add_done_callback(done)

            orchestrator.set_research_hooks(
                lambda: len(orchestrator.research_tasks) < 2, adopt
            )
        if interests is not None:
            shown: set[int] = set()

            def announce() -> None:
                for _ in range(3):
                    offer = interests.next_offer()
                    if offer is None or offer.interest_id in shown:
                        return
                    shown.add(offer.interest_id)
                    interests.store.defer_offer(offer.interest_id, interests._now())
                    print(
                        f"\nsutra> {offer.line}  "
                        f"(/interests approve {offer.interest_id} or /interests reject {offer.interest_id})"
                    )

            interests.set_on_offer(announce)
        count = await orchestrator.start()
        print(f"Connected to the gateway. {count} tools available. Blank line to quit.")
        if memory is not None:
            known = sum(1 for m in memory.list_memories() if m.status == "active")
            print(f"Memory is on ({known} remembered). Type /help for memory commands.")
        else:
            print("Memory is off.")
        if interests is not None:
            interests.start_task()
        if offers is not None:
            offers.start_task()
        if lessons is not None:
            lessons.start_task()
        if idle is not None:
            idle.start_task()
            if idle.enabled:
                print("Idle research is on: I may look into your interests while you're away.")
        if reminder_scheduler is not None:
            reminder_scheduler.start_task()
            print("Reminders are on. Say 'remind me ...', or type /help.")
        try:
            await run_repl(orchestrator, commands=commands if commands._handlers else None)
        finally:
            if reminder_scheduler is not None:
                await reminder_scheduler.stop()
            await orchestrator.cancel_research()
            if interests is not None:
                await interests.stop()
            if lessons is not None:
                await lessons.stop()
            if idle is not None:
                await idle.stop_task()
            if offers is not None:
                await offers.stop_task()
            await orchestrator.flush()
            await orchestrator.flush_graph()
            if memory is not None:
                memory.close()
            if reminder_store is not None:
                reminder_store.close()
            if agents is not None:
                agents.store.close()
            if interests is not None:
                interests.store.close()
            if graph is not None:
                graph.store.close()
            if offers is not None:
                offers.store.close()
            if idle is not None:
                idle.store.close()
            if lessons is not None:
                lessons.store.close()
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
