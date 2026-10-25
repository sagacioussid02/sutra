"""Configuration, read from the environment with an optional .env file."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

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
    )
