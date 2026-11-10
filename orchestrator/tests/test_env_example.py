"""The .env.example documents every variable the config loaders read.

When a new SUTRA_* setting is added to config.py or voice/config.py, add it
here too — with the default value the code uses — or this test fails.
"""

from __future__ import annotations

import re
from pathlib import Path

from sutra_orchestrator.config import load_config
from sutra_orchestrator.dogfood.config import load_dogfood_config
from sutra_orchestrator.voice.config import load_voice_config

EXAMPLE = Path(__file__).parent.parent / ".env.example"
CONFIG_FILES = [
    Path(__file__).parent.parent / "src" / "sutra_orchestrator" / "config.py",
    Path(__file__).parent.parent / "src" / "sutra_orchestrator" / "voice" / "config.py",
    Path(__file__).parent.parent / "src" / "sutra_orchestrator" / "dogfood" / "config.py",
]

_NAME_RE = re.compile(r"^#?\s*([A-Z][A-Z0-9_]*)\s*=")
_LITERAL_RE = re.compile(r'"([A-Z][A-Z0-9_]*)"')


def _documented() -> set[str]:
    """Names the example documents, commented-out placeholders included."""
    names = set()
    for line in EXAMPLE.read_text().splitlines():
        match = _NAME_RE.match(line.strip())
        if match:
            names.add(match.group(1))
    return names


def _active_values() -> dict[str, str]:
    """Uncommented assignments, as a user copying the file would get them."""
    values: dict[str, str] = {}
    for line in EXAMPLE.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = _NAME_RE.match(stripped)
        if match:
            values[match.group(1)] = stripped.split("=", 1)[1].strip()
    return values


def _referenced() -> set[str]:
    """Env names the config loaders actually read."""
    names = set()
    for path in CONFIG_FILES:
        for literal in _LITERAL_RE.findall(path.read_text()):
            if literal.startswith("SUTRA_") or literal in (
                "ANTHROPIC_API_KEY",
                "OPENAI_API_KEY",
            ):
                names.add(literal)
    return names


def test_example_documents_every_variable_the_config_reads():
    missing = _referenced() - _documented()
    assert not missing, (
        "variables read by config.py / voice/config.py but missing from "
        f".env.example: {sorted(missing)}"
    )


def test_example_values_load_cleanly():
    env = _active_values()
    # Secrets are blank placeholders in the example; stand in test values.
    env["SUTRA_TOKEN"] = "t"
    env["ANTHROPIC_API_KEY"] = "k"
    env["OPENAI_API_KEY"] = "sk-test"

    config = load_config(env=env, dotenv_path=None)
    assert config.model == "claude-sonnet-5-5"
    assert config.agent_daily_tokens == 60_000
    assert config.idle_run_tokens == 3000
    assert config.reminders_tz == "America/Denver"

    dogfood = load_dogfood_config(env)
    assert dogfood.out_dir.name == "dogfood" and dogfood.call_budget == 400 and dogfood.lesson_runs == 3

    voice = load_voice_config(env=env, dotenv_path=None)
    assert voice.stt_model == "gpt-4o-transcribe"
    assert voice.tts_voice == "coral"
    assert voice.barge_in == "auto"
    assert voice.min_confidence == 0.5
