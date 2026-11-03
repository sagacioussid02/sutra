"""Voice settings, read from the same environment and .env file as the rest."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import dotenv_values

from ..errors import ConfigError


@dataclass(frozen=True)
class VoiceConfig:
    openai_api_key: str = field(default="", repr=False)
    assistant_name: str = "Sutra"
    stt_model: str = "gpt-4o-transcribe"
    tts_model: str = "gpt-4o-mini-tts"
    tts_voice: str = "coral"
    language: str = ""
    local_stt_model: str = "base.en"
    local_voice: str = ""
    min_confidence: float = 0.5
    filler_delay: float = 1.5
    start_private: bool = False
    record_dir: str = ""
    auto_stop: bool = True
    silence_ms: int = 1200
    no_speech_ms: int = 6000
    conversation: bool = True
    max_background: int = 2
    wait_notice_delay: float = 4.0


def _float(env: Mapping[str, str], name: str, default: float, lo: float, hi: float) -> float:
    raw = env.get(name)
    if raw is None or raw == "":
        return default
    try:
        value = float(raw)
    except ValueError:
        raise ConfigError(f"{name} must be a number, got {raw!r}") from None
    if not lo <= value <= hi:
        raise ConfigError(f"{name} must be between {lo} and {hi}, got {value}")
    return value


def _flag(env: Mapping[str, str], name: str, default: bool) -> bool:
    raw = (env.get(name) or "").strip().lower()
    if not raw:
        return default
    if raw in ("1", "true", "yes", "on"):
        return True
    if raw in ("0", "false", "no", "off"):
        return False
    raise ConfigError(f"{name} must be on or off, got {raw!r}")


def load_voice_config(
    env: Mapping[str, str] | None = None, dotenv_path: str | Path | None = ".env"
) -> VoiceConfig:
    merged: dict[str, str] = {}
    if dotenv_path is not None and Path(dotenv_path).is_file():
        merged.update({k: v for k, v in dotenv_values(dotenv_path).items() if v is not None})
    merged.update(os.environ if env is None else env)

    start = (merged.get("SUTRA_VOICE_MODE") or "cloud").strip().lower()
    if start not in ("cloud", "private"):
        raise ConfigError(f"SUTRA_VOICE_MODE must be cloud or private, got {start!r}")
    return VoiceConfig(
        openai_api_key=merged.get("OPENAI_API_KEY", ""),
        assistant_name=merged.get("SUTRA_ASSISTANT_NAME") or "Sutra",
        stt_model=merged.get("SUTRA_STT_MODEL") or "gpt-4o-transcribe",
        tts_model=merged.get("SUTRA_TTS_MODEL") or "gpt-4o-mini-tts",
        tts_voice=merged.get("SUTRA_TTS_VOICE") or "coral",
        language=merged.get("SUTRA_LANGUAGE", ""),
        local_stt_model=merged.get("SUTRA_LOCAL_STT_MODEL") or "base.en",
        local_voice=merged.get("SUTRA_LOCAL_VOICE", ""),
        min_confidence=_float(merged, "SUTRA_MIN_CONFIDENCE", 0.5, 0.0, 1.0),
        filler_delay=_float(merged, "SUTRA_FILLER_DELAY", 1.5, 0.0, 30.0),
        start_private=start == "private",
        record_dir=merged.get("SUTRA_RECORD_AUDIO_DIR", ""),
        auto_stop=_flag(merged, "SUTRA_AUTO_STOP", True),
        silence_ms=int(_float(merged, "SUTRA_SILENCE_MS", 1200, 300, 5000)),
        no_speech_ms=int(_float(merged, "SUTRA_NO_SPEECH_MS", 6000, 1000, 30000)),
        conversation=_flag(merged, "SUTRA_CONVERSATION", True),
        max_background=int(_float(merged, "SUTRA_MAX_BACKGROUND", 2, 0, 5)),
        wait_notice_delay=_float(merged, "SUTRA_WAIT_NOTICE_DELAY", 4.0, 0.0, 60.0),
    )
