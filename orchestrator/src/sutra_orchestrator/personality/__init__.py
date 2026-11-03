"""Personality: a learned, bounded, rule-gated humor profile.

See ``openspec/changes/personality/``.
"""

from .commands import HumorCommands
from .db import PersonalitySchemaError
from .service import ADJUST_TOOL, HumorPlan, PersonalityService
from .store import PersonalityStore

__all__ = [
    "ADJUST_TOOL",
    "HumorCommands",
    "HumorPlan",
    "PersonalitySchemaError",
    "PersonalityService",
    "PersonalityStore",
]
