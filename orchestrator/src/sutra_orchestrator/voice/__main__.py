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
from ..reminders import ReminderScheduler, ReminderService, ReminderStore
from ..repl import configure_logging
from .config import load_voice_config
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
        FasterWhisperTranscriber(vc.local_stt_model), SaySpeaker(vc.local_voice), "private: local speech, nothing leaves this machine for audio"
    )
    cloud: Engines | None = None
    if vc.openai_api_key:
        hint = f"Names you may hear: {vc.assistant_name}, Sutra, minions, finanxe, twin."
        cloud = Engines(
            OpenAITranscriber(vc.openai_api_key, vc.stt_model, prompt=hint, language=vc.language),
            OpenAISpeaker(vc.openai_api_key, vc.tts_model, vc.tts_voice),
            "cloud: OpenAI speech, audio and spoken replies go to OpenAI",
        )
    else:
        print("OPENAI_API_KEY is not set, so voice starts in private (local) mode.")

    gateway = McpGatewaySession(
        config.gateway_url, config.token, max_result_bytes=config.max_result_bytes
    )
    await gateway.connect()
    try:
        model = AnthropicModel(
            config.api_key, config.model, config.classifier_model,
            extractor_model=config.extractor_model,
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
        reminder_store: ReminderStore | None = None
        reminder_scheduler: ReminderScheduler | None = None
        reminders: ReminderService | None = None
        if config.reminders_enabled:
            reminder_store = ReminderStore(_memory_dir(config.reminders_dir))
            reminders = ReminderService(reminder_store, ZoneInfo(config.reminders_tz))
            reminder_scheduler = ReminderScheduler(reminder_store)
        orchestrator = Orchestrator(
            model=model,
            gateway=gateway,
            classifier=IntentClassifier(model, timeout=config.classifier_timeout),
            memory=memory,
            reminders=reminders,
            max_tool_calls=config.max_tool_calls,
            history_turns=config.history_turns,
            reask_limit=config.reask_limit,
            persona=load_prompt("persona.md").format(name=vc.assistant_name),
            spoken_reasks=True,
        )
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
        )
        session = VoiceSession(
            orchestrator,
            MicRecorder(
                auto_stop=vc.auto_stop, silence_ms=vc.silence_ms, no_speech_ms=vc.no_speech_ms
            ),
            cloud, local, settings, start_private=vc.start_private
        )
        if reminder_scheduler is not None:
            # Fired reminders land in the inbox (see /inbox in the REPL);
            # spoken announcement of a fired reminder is future work that
            # must go through the ask-first notification path.
            reminder_scheduler.start_task()
        try:
            await session.run()
        finally:
            if reminder_scheduler is not None:
                await reminder_scheduler.stop()
            await session.close()
            await orchestrator.flush()
            if memory is not None:
                memory.close()
            if reminder_store is not None:
                reminder_store.close()
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
