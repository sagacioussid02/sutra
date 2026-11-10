"""Settings for the dogfood harness. Every name here is documented in ``.env.example``."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

ORCHESTRATOR_DIR = Path(__file__).resolve().parents[3]
DEFAULT_DIR = "evals/dogfood"


@dataclass(frozen=True)
class DogfoodConfig:
    out_dir: Path
    call_budget: int
    lesson_runs: int
    personal_markers: tuple[str, ...]
    grader_model: str


def _resolve(value: str) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else ORCHESTRATOR_DIR / path


def load_dogfood_config(env: Mapping[str, str] | None = None) -> DogfoodConfig:
    env = os.environ if env is None else env
    markers = tuple(m.strip() for m in env.get("SUTRA_DOGFOOD_PERSONAL_MARKERS", "").split(",") if m.strip())
    return DogfoodConfig(
        out_dir=_resolve(env.get("SUTRA_DOGFOOD_DIR", DEFAULT_DIR)),
        call_budget=max(1, int(env.get("SUTRA_DOGFOOD_CALL_BUDGET", "400"))),
        lesson_runs=max(2, int(env.get("SUTRA_DOGFOOD_LESSON_RUNS", "3"))),
        personal_markers=markers,
        grader_model=env.get("SUTRA_DOGFOOD_GRADER_MODEL", ""),
    )
