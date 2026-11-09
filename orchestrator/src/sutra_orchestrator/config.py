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
    distill_enabled: bool = False
    distill_hours: float = 24.0
    distill_calls: int = 3
    worldstate_enabled: bool = True
    worldstate_timeout: float = 2.0
    worldstate_chars: int = 700
    worldstate_calendar_ttl: int = 5
    worldstate_finance_ttl: int = 15
    events_enabled: bool = False
    events_dir: str = "data"
    events_port: int = 8766
    events_secret: str = ""
    events_cap: int = 5000
    events_retention_days: int = 30
    events_max_attempts: int = 3
    # Speaker identification and addressee detection (voice only). Off by
    # default: with it off, utterances carry no signal and the
    # orchestrator behaves exactly as before this change.
    speaker_enabled: bool = False
    speaker_dir: str = "data"
    speaker_confirm_confidence: float = 0.7
    gossip_url: str = ""
    auth_enabled: bool = False
    auth_mode_questions: int = 1
    auth_action_need: int = 2
    auth_tools: str = ""
    auth_dir: str = "data"
    start_mode: str = "full"
    limited_tools: tuple[str, ...] = ()
    duress_phrase: str = field(default="", repr=False)  # never shown or logged
    safety_dir: str = "data"
    assistant_gender: str = "feminine"
    activation: str = "button"
    wake_words: tuple[str, ...] = ("hey sutra", "sutra")
    hangout_voices: str = ""
    feeds_enabled: bool = True
    home_area: str = ""
    news_enabled: bool = False
    news_topics: tuple[str, ...] = ()
    units: str = "imperial"
    life_enabled: bool = True
    life_dir: str = "data"
    humor_enabled: bool = True
    personality_dir: str = "data"
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
    # Propose-a-patch: draft code on a branch for review. Off unless asked for.
    patches_enabled: bool = False
    patches_dir: str = "~/.sutra/patches"
    patches_max_tool_calls: int = 20
    patches_run_tokens: int = 20_000
    patches_timeout_s: int = 600
    patches_daily_runs: int = 2
    patches_daily_tokens: int = 60_000
    patches_test_command: str = ""
    patches_test_dir: str = "orchestrator"
    patches_test_timeout_s: int = 300
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
        distill_enabled=_bool(merged, "SUTRA_DISTILL", False),
        distill_hours=float(merged.get("SUTRA_DISTILL_HOURS") or 24.0),
        distill_calls=_int(merged, "SUTRA_DISTILL_CALLS", 3),
        worldstate_enabled=_bool(merged, "SUTRA_WORLDSTATE", True),
        worldstate_timeout=float(merged.get("SUTRA_WORLDSTATE_TIMEOUT") or 2.0),
        worldstate_chars=_int(merged, "SUTRA_WORLDSTATE_CHARS", 700),
        worldstate_calendar_ttl=_int(merged, "SUTRA_WORLDSTATE_CALENDAR_TTL", 5),
        worldstate_finance_ttl=_int(merged, "SUTRA_WORLDSTATE_FINANCE_TTL", 15),
        events_enabled=_bool(merged, "SUTRA_EVENTS", False),
        events_dir=merged.get("SUTRA_EVENTS_DIR") or merged.get("SUTRA_MEMORY_DIR") or "data",
        events_port=_int(merged, "SUTRA_EVENTS_PORT", 8766),
        events_secret=merged.get("SUTRA_EVENTS_SECRET") or "",
        events_cap=_int(merged, "SUTRA_EVENTS_CAP", 5000),
        events_retention_days=_int(merged, "SUTRA_EVENTS_RETENTION_DAYS", 30),
        events_max_attempts=_int(merged, "SUTRA_EVENTS_MAX_ATTEMPTS", 3),
        speaker_enabled=_bool(merged, "SUTRA_SPEAKER", False),
        speaker_dir=merged.get("SUTRA_SPEAKER_DIR") or merged.get("SUTRA_MEMORY_DIR") or "data",
        speaker_confirm_confidence=_confidence(merged, "SUTRA_SPEAKER_CONFIRM_CONFIDENCE", 0.7),
        auth_enabled=_bool(merged, "SUTRA_AUTH", False),
        auth_mode_questions=_int(merged, "SUTRA_AUTH_MODE_QUESTIONS", 1),
        auth_action_need=_int(merged, "SUTRA_AUTH_ACTION_NEED", 2),
        auth_tools=merged.get("SUTRA_AUTH_TOOLS", ""),
        auth_dir=merged.get("SUTRA_AUTH_DIR") or merged.get("SUTRA_MEMORY_DIR") or "data",
        start_mode=_choice(merged, "SUTRA_START_MODE", "full", ("full", "limited", "off")),
        limited_tools=tuple(t.strip() for t in (merged.get("SUTRA_LIMITED_TOOLS") or "").split(",") if t.strip()),
        duress_phrase=_duress(merged),
        safety_dir=merged.get("SUTRA_SAFETY_DIR") or merged.get("SUTRA_MEMORY_DIR") or "data",
        assistant_gender=_choice(merged, "SUTRA_ASSISTANT_GENDER", "feminine", ("feminine", "masculine", "neutral")),
        activation=_choice(merged, "SUTRA_ACTIVATION", "button", ("button", "wake")),
        wake_words=tuple(w.strip().lower() for w in (merged.get("SUTRA_WAKE_WORDS") or "hey sutra,sutra").split(",") if w.strip()),
        gossip_url=_gossip_url(merged),
        hangout_voices=merged.get("SUTRA_HANGOUT_VOICES", ""),
        feeds_enabled=_bool(merged, "SUTRA_FEEDS", True),
        home_area=" ".join((merged.get("SUTRA_HOME_AREA") or "").split()),
        news_enabled=_bool(merged, "SUTRA_NEWS", False),
        news_topics=tuple(t.strip() for t in (merged.get("SUTRA_NEWS_TOPICS") or "").split(",") if t.strip()),
        units=_units(merged),
        life_enabled=_bool(merged, "SUTRA_LIFE", True),
        life_dir=merged.get("SUTRA_LIFE_DIR") or merged.get("SUTRA_MEMORY_DIR") or "data",
        humor_enabled=_bool(merged, "SUTRA_HUMOR", True),
        personality_dir=merged.get("SUTRA_PERSONALITY_DIR") or merged.get("SUTRA_MEMORY_DIR") or "data",
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
        patches_enabled=_bool(merged, "SUTRA_PATCHES", False),
        patches_dir=merged.get("SUTRA_PATCHES_DIR") or "~/.sutra/patches",
        patches_max_tool_calls=_int(merged, "SUTRA_PATCHES_MAX_TOOL_CALLS", 20),
        patches_run_tokens=_int(merged, "SUTRA_PATCHES_RUN_TOKENS", 20_000),
        patches_timeout_s=_int(merged, "SUTRA_PATCHES_TIMEOUT", 600),
        patches_daily_runs=_int(merged, "SUTRA_PATCHES_DAILY_RUNS", 2),
        patches_daily_tokens=_int(merged, "SUTRA_PATCHES_DAILY_TOKENS", 60_000),
        patches_test_command=merged.get("SUTRA_PATCHES_TEST_COMMAND") or "",
        patches_test_dir=merged.get("SUTRA_PATCHES_TEST_DIR") or "orchestrator",
        patches_test_timeout_s=_int(merged, "SUTRA_PATCHES_TEST_TIMEOUT", 300),
        reminders_enabled=_bool(merged, "SUTRA_REMINDERS", True),
        reminders_dir=merged.get("SUTRA_REMINDERS_DIR")
        or merged.get("SUTRA_MEMORY_DIR")
        or "data",
        reminders_tz=_timezone(merged),
    )


def _confidence(env: Mapping[str, str], name: str, default: float) -> float:
    raw = env.get(name)
    if raw is None or raw == "":
        return default
    try:
        value = float(raw)
    except ValueError:
        raise ConfigError(f"{name} must be a number, got {raw!r}") from None
    if not 0.0 <= value <= 1.0:
        raise ConfigError(f"{name} must be between 0 and 1, got {value}")
    return value


def _gossip_url(env: Mapping[str, str]) -> str:
    raw = (env.get("SUTRA_GOSSIP_URL") or "").strip()
    if not raw:
        return ""
    from .hangout import check_url

    try:
        return check_url(raw)
    except ValueError as exc:
        raise ConfigError(f"SUTRA_GOSSIP_URL {exc}, got {raw!r}") from None


def _choice(env: Mapping[str, str], name: str, default: str, allowed: tuple[str, ...]) -> str:
    raw = (env.get(name) or default).strip().lower()
    if raw not in allowed:
        raise ConfigError(f"{name} must be one of {', '.join(allowed)}, got {raw!r}")
    return raw


def _duress(env: Mapping[str, str]) -> str:
    phrase = " ".join((env.get("SUTRA_DURESS_PHRASE") or "").split())
    if phrase and len(phrase.split()) < 2 and len(phrase) < 8:
        raise ConfigError("SUTRA_DURESS_PHRASE must be a phrase of at least two words (or eight characters)")
    return phrase


def _units(env: Mapping[str, str]) -> str:
    raw = (env.get("SUTRA_UNITS") or "imperial").strip().lower()
    if raw not in ("imperial", "metric"):
        raise ConfigError(f"SUTRA_UNITS must be imperial or metric, got {raw!r}")
    return raw


def _timezone(env: Mapping[str, str]) -> str:
    raw = env.get("SUTRA_REMINDERS_TZ") or "America/Denver"
    try:
        ZoneInfo(raw)
    except (ZoneInfoNotFoundError, ValueError):
        raise ConfigError(f"SUTRA_REMINDERS_TZ is not a known timezone: {raw!r}") from None
    return raw
