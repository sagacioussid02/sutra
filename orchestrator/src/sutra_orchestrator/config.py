"""Configuration, read from the environment with an optional .env file."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dotenv import dotenv_values

from .errors import ConfigError

DEFAULT_GATEWAY_URL = "http://127.0.0.1:8765"
DEFAULT_MODEL = "claude-sonnet-5-5"
DEFAULT_CLASSIFIER_MODEL = "claude-haiku-5-5"


@dataclass(frozen=True)
class Config:
    gateway_url: str
    # Secrets are excluded from repr so they cannot leak through logging.
    token: str = field(repr=False)
    api_key: str = field(repr=False)
    model: str = DEFAULT_MODEL
    classifier_model: str = DEFAULT_CLASSIFIER_MODEL
    max_tool_calls: int = 6
    history_turns: int = 20
    max_result_bytes: int = 16_000
    reask_limit: int = 2
    classifier_timeout: float = 8.0
    extractor_model: str = DEFAULT_CLASSIFIER_MODEL
    memory_enabled: bool = True
    memory_dir: str = "data"
    record_replies: bool = True
    episode_hot_days: int = 30
    interests_enabled: bool = True
    reflection_enabled: bool = True
    reflection_hours: int = 24
    reflection_days: int = 30
    reflection_exclude_tools: tuple[str, ...] = ("finanxe_",)
    nudge_hours: int = 24
    interests_dir: str = "data"
    graph_enabled: bool = True
    graph_dir: str = "data"
    offers_enabled: bool = True
    offers_dir: str = "data"
    offers_daily_max: int = 4
    offers_calls_per_day: int = 200
    offers_urgent_sources: tuple[str, ...] = ()
    lessons_enabled: bool = True
    lessons_reflection: bool = True
    lessons_dir: str = "data"
    idle_enabled: bool = False
    idle_dir: str = "data"
    idle_daily_runs: int = 1
    idle_min_hours: int = 48
    idle_max_searches: int = 2
    idle_run_tokens: int = 3000
    agents_enabled: bool = True
    agent_model: str = DEFAULT_CLASSIFIER_MODEL
    agent_tools: tuple[str, ...] = ()
    agents_dir: str = "data"
    agent_max_searches: int = 5
    agent_max_tool_calls: int = 5
    agent_run_tokens: int = 8000
    agent_timeout_s: int = 180
    agent_daily_runs: int = 3
    agent_daily_tokens: int = 60_000
    reminders_enabled: bool = True
    reminders_dir: str = "data"
    # Wall-clock reminder times ("at 5pm") are read in this timezone.
    reminders_tz: str = "America/Denver"


def _int(env: Mapping[str, str], name: str, default: int) -> int:
    raw = env.get(name)
    if raw is None or raw == "":
        return default
    try:
        value = int(raw)
    except ValueError:
        raise ConfigError(f"{name} must be an integer, got {raw!r}") from None
    if value < 1:
        raise ConfigError(f"{name} must be at least 1, got {value}")
    return value


def _bool(env: Mapping[str, str], name: str, default: bool) -> bool:
    raw = env.get(name)
    if raw is None or raw == "":
        return default
    value = raw.strip().lower()
    if value in ("1", "true", "yes", "on"):
        return True
    if value in ("0", "false", "no", "off"):
        return False
    raise ConfigError(f"{name} must be on or off, got {raw!r}")


def load_config(
    env: Mapping[str, str] | None = None, dotenv_path: str | Path | None = ".env"
) -> Config:
    """Build a Config. Real environment variables win over the .env file."""
    merged: dict[str, str] = {}
    if dotenv_path is not None and Path(dotenv_path).is_file():
        merged.update({k: v for k, v in dotenv_values(dotenv_path).items() if v is not None})
    merged.update(os.environ if env is None else env)

    missing = [name for name in ("SUTRA_TOKEN", "ANTHROPIC_API_KEY") if not merged.get(name)]
    if missing:
        raise ConfigError(
            "missing required configuration: "
            + ", ".join(missing)
            + " (set it in the environment or in orchestrator/.env; see .env.example)"
        )

    return Config(
        gateway_url=merged.get("SUTRA_GATEWAY_URL") or DEFAULT_GATEWAY_URL,
        token=merged["SUTRA_TOKEN"],
        api_key=merged["ANTHROPIC_API_KEY"],
        model=merged.get("SUTRA_MODEL") or DEFAULT_MODEL,
        classifier_model=merged.get("SUTRA_CLASSIFIER_MODEL") or DEFAULT_CLASSIFIER_MODEL,
        max_tool_calls=_int(merged, "SUTRA_MAX_TOOL_CALLS", 6),
        history_turns=_int(merged, "SUTRA_HISTORY_TURNS", 20),
        max_result_bytes=_int(merged, "SUTRA_MAX_RESULT_BYTES", 16_000),
        reask_limit=_int(merged, "SUTRA_REASK_LIMIT", 2),
        extractor_model=merged.get("SUTRA_EXTRACTOR_MODEL") or DEFAULT_CLASSIFIER_MODEL,
        memory_enabled=_bool(merged, "SUTRA_MEMORY", True),
        memory_dir=merged.get("SUTRA_MEMORY_DIR") or "data",
        record_replies=_bool(merged, "SUTRA_RECORD_REPLIES", True),
        episode_hot_days=_int(merged, "SUTRA_EPISODE_HOT_DAYS", 30),
        interests_enabled=_bool(merged, "SUTRA_INTERESTS", True),
        reflection_enabled=_bool(merged, "SUTRA_REFLECTION", True),
        reflection_hours=_int(merged, "SUTRA_REFLECTION_HOURS", 24),
        reflection_days=_int(merged, "SUTRA_REFLECTION_DAYS", 30),
        reflection_exclude_tools=(
            tuple(
                t.strip()
                for t in merged["SUTRA_REFLECTION_EXCLUDE_TOOLS"].split(",")
                if t.strip()
            )
            if merged.get("SUTRA_REFLECTION_EXCLUDE_TOOLS") is not None
            else ("finanxe_",)
        ),
        nudge_hours=_int(merged, "SUTRA_NUDGE_HOURS", 24),
        interests_dir=merged.get("SUTRA_INTERESTS_DIR") or merged.get("SUTRA_MEMORY_DIR") or "data",
        graph_enabled=_bool(merged, "SUTRA_GRAPH", True),
        graph_dir=merged.get("SUTRA_GRAPH_DIR") or merged.get("SUTRA_MEMORY_DIR") or "data",
        offers_enabled=_bool(merged, "SUTRA_OFFERS", True),
        offers_dir=merged.get("SUTRA_OFFERS_DIR") or merged.get("SUTRA_MEMORY_DIR") or "data",
        offers_daily_max=_int(merged, "SUTRA_OFFERS_DAILY_MAX", 4),
        offers_calls_per_day=_int(merged, "SUTRA_OFFERS_CALLS", 200),
        offers_urgent_sources=tuple(
            t.strip() for t in (merged.get("SUTRA_OFFERS_URGENT_SOURCES") or "").split(",") if t.strip()
        ),
        lessons_enabled=_bool(merged, "SUTRA_LESSONS", True),
        lessons_reflection=_bool(merged, "SUTRA_LESSONS_REFLECTION", True),
        lessons_dir=merged.get("SUTRA_LESSONS_DIR") or merged.get("SUTRA_MEMORY_DIR") or "data",
        idle_enabled=_bool(merged, "SUTRA_IDLE_RESEARCH", False),
        idle_dir=merged.get("SUTRA_IDLE_DIR") or merged.get("SUTRA_MEMORY_DIR") or "data",
        idle_daily_runs=_int(merged, "SUTRA_IDLE_DAILY_RUNS", 1),
        idle_min_hours=_int(merged, "SUTRA_IDLE_MIN_HOURS", 48),
        idle_max_searches=_int(merged, "SUTRA_IDLE_MAX_SEARCHES", 2),
        idle_run_tokens=_int(merged, "SUTRA_IDLE_RUN_TOKENS", 3000),
        agents_enabled=_bool(merged, "SUTRA_AGENTS", True),
        agent_model=merged.get("SUTRA_AGENT_MODEL") or DEFAULT_CLASSIFIER_MODEL,
        agent_tools=tuple(
            t.strip() for t in (merged.get("SUTRA_AGENT_TOOLS") or "").split(",") if t.strip()
        ),
        agents_dir=merged.get("SUTRA_AGENTS_DIR") or merged.get("SUTRA_MEMORY_DIR") or "data",
        agent_max_searches=_int(merged, "SUTRA_AGENT_MAX_SEARCHES", 5),
        agent_max_tool_calls=_int(merged, "SUTRA_AGENT_MAX_TOOL_CALLS", 5),
        agent_run_tokens=_int(merged, "SUTRA_AGENT_RUN_TOKENS", 8000),
        agent_timeout_s=_int(merged, "SUTRA_AGENT_TIMEOUT", 180),
        agent_daily_runs=_int(merged, "SUTRA_AGENT_DAILY_RUNS", 3),
        agent_daily_tokens=_int(merged, "SUTRA_AGENT_DAILY_TOKENS", 60_000),
        reminders_enabled=_bool(merged, "SUTRA_REMINDERS", True),
        reminders_dir=merged.get("SUTRA_REMINDERS_DIR")
        or merged.get("SUTRA_MEMORY_DIR")
        or "data",
        reminders_tz=_timezone(merged),
    )


def _timezone(env: Mapping[str, str]) -> str:
    raw = env.get("SUTRA_REMINDERS_TZ") or "America/Denver"
    try:
        ZoneInfo(raw)
    except (ZoneInfoNotFoundError, ValueError):
        raise ConfigError(f"SUTRA_REMINDERS_TZ is not a known timezone: {raw!r}") from None
    return raw
