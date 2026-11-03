"""Idle research: budgeted background research over approved interests and recent plans.

See ``openspec/changes/idle-research/``.
"""

from .commands import IdleCommands
from .db import IdleSchemaError
from .factory import build_idle
from .picker import Pick, Picker, Topic, brief_problem
from .service import SOURCE, IdleResearcher
from .store import IdleRun, IdleStore

__all__ = [
    "IdleCommands",
    "IdleResearcher",
    "IdleRun",
    "IdleSchemaError",
    "IdleStore",
    "Pick",
    "Picker",
    "SOURCE",
    "Topic",
    "brief_problem",
    "build_idle",
]
