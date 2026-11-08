"""Propose-a-patch: draft a missing capability on a git branch, never apply it.

A run works in a worktree cut from ``main`` with three confined tools, cannot touch the protected
safety layer, runs tests only under an OS sandbox, and ends as an untrusted proposal for a human to
review and merge. See ``openspec/changes/propose-a-patch/``.
"""

from .commands import PatchCommands
from .db import PatchSchemaError
from .factory import build_patch_service, maybe_build_patch_service
from .protected import PROTECTED, is_protected
from .service import PatchResult, PatchService
from .store import PatchRow, PatchStore

PROPOSE_TOOL = "propose_capability"

__all__ = [
    "PROPOSE_TOOL",
    "PROTECTED",
    "PatchCommands",
    "PatchResult",
    "PatchRow",
    "PatchSchemaError",
    "PatchService",
    "PatchStore",
    "build_patch_service",
    "maybe_build_patch_service",
    "is_protected",
]
