"""``python -m sutra_orchestrator``: talk to the Sutra gateway in text."""

from __future__ import annotations

import argparse
import asyncio
import logging
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
from .personality import HumorCommands, PersonalityService, PersonalityStore
from .life import LifeCommands, LifeService, LifeStore
from .feeds import FeedCommands, build_feeds
from .hangout import HangoutCommands, HangoutService, HttpGroupClient, parse_voices
from .safety import Mode, ModeCommands, SafetyService
from .auth import AuthCommands, build_auth
from .agents.factory import build_agent_service
from .reminders import ReminderScheduler, ReminderService, ReminderStore
from .reminders.commands import ReminderCommands
from .repl import CommandSet, configure_logging, run_repl


log = logging.getLogger("sutra_orchestrator")


def watch_task(name: str, task: asyncio.Task[None]) -> asyncio.Task[None]:
    """Keep a background task's handle and make its death loud.

    Every background loop is written to survive its own errors, so a
    task that still ends on one is a real failure — and an invisible
    one unless something says so: nobody awaits these handles.
    """

    def died(done: asyncio.Task[None]) -> None:
        if done.cancelled():
            return
        exc = done.exception()
        if exc is not None:
            log.error(
                "background task %s stopped (%s); it will not run again",
                name,
                type(exc).__name__,
                exc_info=exc,
            )

    task.add_done_callback(died)
    return task


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
        personality = (
            PersonalityService(PersonalityStore(_memory_dir(config.personality_dir)), model)
            if config.humor_enabled
            else None
        )
        humor_commands = HumorCommands(personality) if personality is not None else None
        life = None
        if config.life_enabled:
            life = LifeService(
                LifeStore(_memory_dir(config.life_dir)), offers=offers, model=model, tz=ZoneInfo(config.reminders_tz),
                spend=offers.spend_call if offers is not None else None,
            )
            if graph is not None:
                graph.add_listener(life.on_episode)  # people and plans come from closed conversations
        life_commands = LifeCommands(life) if life is not None else None
        feeds = build_feeds(config, offers, interests, reminder_store, life)
        feed_commands = FeedCommands(feeds) if feeds is not None else None
        hangout = (
            HangoutService(HttpGroupClient(config.gossip_url), parse_voices(config.hangout_voices))
            if config.gossip_url
            else None
        )
        hangout_commands = HangoutCommands(hangout, config.gossip_url) if hangout is not None else None
        safety = SafetyService(
            _memory_dir(config.safety_dir),
            start=Mode(config.start_mode),
            extra_tools=config.limited_tools,
            duress_phrase=config.duress_phrase,
        )
        mode_commands = ModeCommands(safety)
        auth = build_auth(
            config, model, _memory_dir(config.auth_dir), safety, life, reminder_store,
            spend=offers.spend_call if offers is not None else None,
        )
        auth_commands = AuthCommands(auth)
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
            idle_commands, lesson_commands, humor_commands, life_commands,
            feed_commands, hangout_commands, mode_commands, auth_commands, memory_commands
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
            personality=personality,
            life=life,
            feeds=feeds,
            hangout=hangout,
            safety=safety,
            auth=auth,
            assistant_gender=config.assistant_gender,
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
        # Every unprompted or outward-reaching path asks the one mode before it acts.
        quiet = lambda: not safety.proactive_ok  # noqa: E731
        if offers is not None:
            offers.arbiter.set_quiet(quiet)
        if feeds is not None:
            feeds.set_quiet(quiet)
        if idle is not None:
            idle.set_quiet(quiet)
        count = await orchestrator.start()
        print(f"Connected to the gateway. {count} tools available. Blank line to quit.")
        if safety.mode is not Mode.FULL:
            print(f"Mode is {safety.mode.value}. Type /mode full to go back to full.")
        if memory is not None:
            known = sum(1 for m in memory.list_memories() if m.status == "active")
            print(f"Memory is on ({known} remembered). Type /help for memory commands.")
        else:
            print("Memory is off.")
        background_tasks: list[asyncio.Task[None]] = []
        if interests is not None:
            background_tasks.append(watch_task("interests", interests.start_task()))
        if offers is not None:
            background_tasks.append(watch_task("offers", offers.start_task()))
        if lessons is not None:
            background_tasks.append(watch_task("lessons", lessons.start_task()))
        if life is not None:
            background_tasks.append(watch_task("life", life.start_task()))
        if feeds is not None:
            background_tasks.append(watch_task("feeds", feeds.start_task()))
        if idle is not None:
            background_tasks.append(watch_task("idle research", idle.start_task()))
            if idle.enabled:
                print("Idle research is on: I may look into your interests while you're away.")
        if reminder_scheduler is not None:
            background_tasks.append(watch_task("reminders", reminder_scheduler.start_task()))
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
            if life is not None:
                await life.stop()
            if feeds is not None:
                await feeds.stop()
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
            if personality is not None:
                personality.store.close()
            if life is not None:
                life.store.close()
            auth.store.close()
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
