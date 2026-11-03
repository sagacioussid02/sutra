"""Build lessons from configuration (shared by the text and voice clients)."""

from __future__ import annotations

from pathlib import Path

from ..classifier import IntentClassifier  # noqa: F401  (documented dependency of the probes)
from ..config import Config
from ..offers import OffersService
from .probes import check_lesson
from .reflect import Reflector
from .service import LessonService, render_block
from .store import LessonStore


def build_lessons(config: Config, model, memory, offers: OffersService | None, directory: Path) -> LessonService:
    """``model`` is the real AnthropicModel: it reflects, and it is what the probes run against."""
    store = LessonStore(directory)
    reflector = None
    if config.lessons_reflection:
        source = memory if hasattr(memory, "recent_exchanges") else None
        reflector = Reflector(source, store, model, exclude_tool_prefixes=config.reflection_exclude_tools)

    async def checker(text: str) -> tuple[str, str]:
        return await check_lesson(text, model, model, render_block)

    return LessonService(store, offers=offers, reflector=reflector, checker=checker)
