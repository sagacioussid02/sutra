"""``python -m sutra_orchestrator.voice``: talk to Sutra with push-to-talk."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

from ..classifier import IntentClassifier
from ..config import load_config
from ..errors import OrchestratorError
from ..gateway import McpGatewaySession
from ..__main__ import _memory_dir
from ..memstore import SqliteMemory
from ..memstore.commands import MemoryCommands  # noqa: F401  (kept for parity with the REPL)
from ..model import AnthropicModel
from ..orchestrator import Orchestrator
from ..prompts import load_prompt
from ..agents.factory import build_agent_service
from ..interests import InterestService, InterestStore, Reflector
from ..offers import build_graph_and_offers
from ..idle import build_idle
from ..lessons import build_lessons
from ..personality import PersonalityService, PersonalityStore
from ..life import LifeService, LifeStore
from ..feeds import build_feeds
from ..hangout import HangoutService, HttpGroupClient, parse_voices
from ..safety import Mode, SafetyService
from ..auth import build_auth
from .wake import WakeMatcher
from ..reminders import ReminderScheduler, ReminderService, ReminderStore
from ..repl import configure_logging
from .config import load_voice_config
from .hints import build_hint, memory_names
from .devices import output_is_headphones
from .local_engines import FasterWhisperTranscriber, SaySpeaker
from .loop import VoiceSession, VoiceSettings
from .openai_engines import OpenAISpeaker, OpenAITranscriber
from .recorder import MicRecorder
from .types import Engines


async def _run(verbose: bool) -> int:
    config = load_config()
    vc = load_voice_config()
    configure_logging(verbose, [config.token, config.api_key, vc.openai_api_key])

    local = Engines(
        FasterWhisperTranscriber(vc.local_stt_model, vc.local_stt_language or None),
        SaySpeaker(vc.local_voice, vc.local_voice_hi), "private: local speech, nothing leaves this machine for audio"
    )
    cloud: Engines | None = None
    if not vc.openai_api_key:
        print("OPENAI_API_KEY is not set, so voice starts in private (local) mode.")

    gateway = McpGatewaySession(
        config.gateway_url, config.token, max_result_bytes=config.max_result_bytes
    )
    await gateway.connect()
    try:
        model = AnthropicModel(
            config.api_key, config.model, config.classifier_model,
            extractor_model=config.extractor_model,
            agent_model=config.agent_model,
        )
        memory = None
        if config.memory_enabled:
            memory = SqliteMemory(
                _memory_dir(config.memory_dir),
                extractor=model,
                record_replies=config.record_replies,
                hot_days=config.episode_hot_days,
                on_notice=lambda notice: print(f"  {notice}"),
            )
        if vc.openai_api_key:
            # Names the user has told Sutra (a city, a person) go to the recognizer as a vocabulary hint, so
            # "Orem" is not heard as "Zoram". Only these words are sent, and only in cloud mode.
            remembered = (
                memory_names(m.content for m in memory.list_memories() if m.status == "active")
                if memory is not None
                else []
            )
            if config.life_enabled:  # the names of people the user has mentioned are vocabulary too
                people = LifeStore(_memory_dir(config.life_dir))
                remembered = [*remembered, *[p.name for p in people.people()]]
                people.close()
            hint = build_hint(vc.assistant_name, vc.stt_hints, remembered)
            cloud = Engines(
                OpenAITranscriber(vc.openai_api_key, vc.stt_model, prompt=hint, language=vc.language),
                OpenAISpeaker(
                    vc.openai_api_key, vc.tts_model, vc.tts_voice,
                    **({"instructions": vc.tts_style} if vc.tts_style else {}),
                ),
                "cloud: OpenAI speech, audio and spoken replies go to OpenAI",
            )
        reminder_store: ReminderStore | None = None
        reminder_scheduler: ReminderScheduler | None = None
        reminders: ReminderService | None = None
        if config.reminders_enabled:
            reminder_store = ReminderStore(_memory_dir(config.reminders_dir))
            reminders = ReminderService(reminder_store, ZoneInfo(config.reminders_tz))

            def deliver(entry) -> None:
                session.deliver_reminder(entry, entry.text, entry.late)

            reminder_scheduler = ReminderScheduler(reminder_store, on_deliver=deliver)
        interests = None
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
        graph, offers = build_graph_and_offers(config, model, _memory_dir)
        agents = None
        if config.agents_enabled:
            agents = build_agent_service(
                config, model, gateway, lambda: orchestrator.gateway_tools,
                _memory_dir(config.agents_dir), ZoneInfo(config.reminders_tz),
            )
        lessons = (
            build_lessons(config, model, memory, offers, _memory_dir(config.lessons_dir))
            if config.lessons_enabled
            else None
        )
        personality = (
            PersonalityService(PersonalityStore(_memory_dir(config.personality_dir)), model)
            if config.humor_enabled
            else None
        )
        life = None
        if config.life_enabled:
            life = LifeService(
                LifeStore(_memory_dir(config.life_dir)), offers=offers, model=model, tz=ZoneInfo(config.reminders_tz),
                spend=offers.spend_call if offers is not None else None,
            )
            if graph is not None:
                graph.add_listener(life.on_episode)
        feeds = build_feeds(config, offers, interests, reminder_store, life)
        hangout = (
            HangoutService(HttpGroupClient(config.gossip_url), parse_voices(config.hangout_voices))
            if config.gossip_url
            else None
        )
        safety = SafetyService(
            _memory_dir(config.safety_dir),
            start=Mode(config.start_mode),
            extra_tools=config.limited_tools,
            duress_phrase=config.duress_phrase,
        )
        auth = build_auth(
            config, model, _memory_dir(config.auth_dir), safety, life, reminder_store,
            spend=offers.spend_call if offers is not None else None,
        )
        idle = build_idle(
            config, model, _memory_dir(config.idle_dir),
            interests=interests, graph=graph, agents=agents, offers=offers,
            last_activity=lambda: orchestrator.last_activity,
            busy=lambda: (
                orchestrator.pending is not None
                or bool(orchestrator.research_tasks)
                or session.busy()
            ),
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
            persona=load_prompt("persona.md").format(name=vc.assistant_name),
            spoken_reasks=True,
        )
        # Every unprompted or outward-reaching path asks the one mode before it acts.
        quiet = lambda: not safety.proactive_ok  # noqa: E731
        if offers is not None:
            offers.arbiter.set_quiet(quiet)
        if feeds is not None:
            feeds.set_quiet(quiet)
        if idle is not None:
            idle.set_quiet(quiet)
        count = await orchestrator.start()
        print(f"Connected to the gateway. {count} tools available. I'm {vc.assistant_name}.")
        settings = VoiceSettings(
            min_confidence=vc.min_confidence,
            reask_limit=config.reask_limit,
            filler_delay=vc.filler_delay,
            conversation=vc.conversation,
            max_background=vc.max_background,
            wait_notice_delay=vc.wait_notice_delay,
            record_dir=Path(vc.record_dir).expanduser() if vc.record_dir else None,
            barge_in=output_is_headphones() if vc.barge_in == "auto" else vc.barge_in == "on",
            stream=vc.stream_reply,
            activation=config.activation,
        )
        session = VoiceSession(
            orchestrator,
            MicRecorder(
                auto_stop=vc.auto_stop, silence_ms=vc.silence_ms, no_speech_ms=vc.no_speech_ms
            ),
            cloud, local, settings, start_private=vc.start_private,
            on_reminder_spoken=(
                (lambda entry: reminder_store.mark_seen(entry.id)) if reminder_store else None
            ),
        )
        if interests is not None:
            session.attach_interests(interests)
            interests.start_task()
        if offers is not None:
            session.attach_offers(offers)
            offers.start_task()
        session.attach_safety(safety)
        session.attach_auth(auth)
        if config.activation == "wake":
            session.attach_wake(WakeMatcher(config.wake_words))
        if lessons is not None:
            lessons.start_task()
        if life is not None:
            life.start_task()
        if feeds is not None:
            feeds.start_task()
        if idle is not None:
            idle.start_task()
        warm = None
        if cloud is not None and hasattr(cloud.speaker, "prewarm"):
            # The "hmm, one sec" fillers are synthesized once now, so they play at once when needed.
            warm = asyncio.create_task(cloud.speaker.prewarm(settings.fillers))
        if agents is not None:
            orchestrator.set_research_hooks(session.can_start_job, session.adopt_research)
        if reminder_scheduler is not None and reminder_store is not None:
            # Reminders that fired but were never heard (the last run ended
            # first) are said now, marked late.
            for entry in reminder_store.list_inbox(unseen_only=True):
                session.deliver_reminder(entry, entry.text, late=True)
            reminder_scheduler.start_task()
        try:
            await session.run()
        finally:
            if warm is not None:
                warm.cancel()
            if reminder_scheduler is not None:
                await reminder_scheduler.stop()
            await session.close()
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
    parser = argparse.ArgumentParser(prog="sutra_orchestrator.voice", description=__doc__)
    parser.add_argument("--verbose", action="store_true", help="log tool names and timings (never secrets)")
    args = parser.parse_args()
    try:
        sys.exit(asyncio.run(_run(args.verbose)))
    except OrchestratorError as exc:
        print(f"sutra_orchestrator.voice: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
