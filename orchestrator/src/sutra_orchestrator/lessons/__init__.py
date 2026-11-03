"""Self-learning: proposed, user-approved, probe-gated lessons with two bounded effects.

See ``openspec/changes/self-learning/``.
"""

from .commands import LessonCommands
from .db import LessonSchemaError
from .factory import build_lessons
from .reflect import Reflector, RunResult, outcome_proposals
from .rules import Proposal, clean_text, guidance, tripwire
from .service import RETIRE_TOOL, SOURCE, LessonService, render_block
from .store import Lesson, LessonStore

__all__ = [
    "Lesson",
    "LessonCommands",
    "LessonSchemaError",
    "LessonService",
    "LessonStore",
    "Proposal",
    "RETIRE_TOOL",
    "Reflector",
    "RunResult",
    "SOURCE",
    "build_lessons",
    "clean_text",
    "guidance",
    "outcome_proposals",
    "render_block",
    "tripwire",
]
