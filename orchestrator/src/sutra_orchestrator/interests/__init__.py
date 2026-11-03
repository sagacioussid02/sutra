"""Interest profile: topics the user cares about, derived from what they say, approved by them.

See ``openspec/changes/interest-profile/``.
"""

from .commands import InterestCommands
from .db import InterestSchemaError
from .reflect import Reflector, RunResult
from .service import MUTE_TOOL, InterestService, Offer
from .store import InterestRow, InterestStore

__all__ = [
    "InterestCommands",
    "InterestRow",
    "InterestSchemaError",
    "InterestService",
    "InterestStore",
    "MUTE_TOOL",
    "Offer",
    "Reflector",
    "RunResult",
]
