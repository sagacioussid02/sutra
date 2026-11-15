"""Central model registry: one place maps each job to its model.

Every model call in the orchestrator goes through one of these roles.
Change a model by setting the role's environment variable — no code
change, no other file to touch. Defaults preserve today's behavior
exactly; this is a registry, not a model swap.

Roles
-----
conversation  The model that talks to you and picks tools (Anthropic).
classifier    Small model that reads yes/no replies to confirmations.
extractor     Small model that extracts durable facts about you — and
              every forced-schema ("structured") call: the episode
              graph, the offer judge, distill, lessons, life, auth.
agent         Small model the researcher (and the patch drafter) uses.
stt           Cloud speech-to-text (OpenAI).
tts           Cloud text-to-speech (OpenAI).
local_stt     Local speech-to-text (faster-whisper model size).
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class ModelSpec:
    """One role's model: who provides it, which one, and how to flip it."""

    role: str
    provider: str
    default: str
    env_var: str
    description: str


REGISTRY: dict[str, ModelSpec] = {
    "conversation": ModelSpec(
        role="conversation",
        provider="anthropic",
        default="claude-sonnet-5-5",
        env_var="SUTRA_MODEL",
        description="The model that talks to you and picks tools.",
    ),
    "classifier": ModelSpec(
        role="classifier",
        provider="anthropic",
        default="claude-haiku-5-5",
        env_var="SUTRA_CLASSIFIER_MODEL",
        description="Small model that reads yes/no replies to confirmations.",
    ),
    "extractor": ModelSpec(
        role="extractor",
        provider="anthropic",
        default="claude-haiku-5-5",
        env_var="SUTRA_EXTRACTOR_MODEL",
        description=(
            "Small model that extracts durable facts about you, and every "
            "forced-schema call (episode graph, offer judge, distill, "
            "lessons, life, auth)."
        ),
    ),
    "agent": ModelSpec(
        role="agent",
        provider="anthropic",
        default="claude-haiku-5-5",
        env_var="SUTRA_AGENT_MODEL",
        description="Small model the researcher (and the patch drafter) uses.",
    ),
    "stt": ModelSpec(
        role="stt",
        provider="openai",
        default="gpt-4o-transcribe",
        env_var="SUTRA_STT_MODEL",
        description="Cloud speech-to-text.",
    ),
    "tts": ModelSpec(
        role="tts",
        provider="openai",
        default="gpt-4o-mini-tts",
        env_var="SUTRA_TTS_MODEL",
        description="Cloud text-to-speech.",
    ),
    "local_stt": ModelSpec(
        role="local_stt",
        provider="faster-whisper",
        default="base.en",
        env_var="SUTRA_LOCAL_STT_MODEL",
        description="Local speech-to-text model size.",
    ),
}


def roles() -> tuple[str, ...]:
    """The registry's roles, in the order they are documented."""
    return tuple(REGISTRY)


def spec(role: str) -> ModelSpec:
    """The registry entry for a role; raises ValueError for an unknown role."""
    try:
        return REGISTRY[role]
    except KeyError:
        raise ValueError(f"unknown model role: {role!r} (known: {', '.join(REGISTRY)})") from None


def default_model(role: str) -> str:
    """The model a role uses when its environment variable is unset."""
    return spec(role).default


def model_env_var(role: str) -> str:
    """The environment variable that flips a role's model."""
    return spec(role).env_var


def resolve_model(role: str, env: Mapping[str, str] | None = None) -> str:
    """A role's model: its environment variable wins, else the default.

    A blank value counts as unset, matching how the config loaders treat
    every other variable. ``env`` defaults to the real environment.
    """
    entry = spec(role)
    raw = (env if env is not None else os.environ).get(entry.env_var)
    return raw.strip() if raw and raw.strip() else entry.default
