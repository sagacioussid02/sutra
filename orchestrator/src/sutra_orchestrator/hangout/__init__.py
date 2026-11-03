"""Hangout: a voiced, opt-in, clearly fictional group chat kept apart from the assistant.

See ``openspec/changes/gossip-hangout/``.
"""

from .commands import HangoutCommands
from .service import (
    ENTRY,
    LEFT,
    UNREACHABLE,
    WITHHELD,
    GroupClient,
    HangoutReply,
    HangoutService,
    HttpGroupClient,
    Line,
    check_url,
    is_start,
    is_stop,
    lines_from,
    parse_voices,
)

__all__ = [
    "ENTRY", "GroupClient", "HangoutCommands", "HangoutReply", "HangoutService", "HttpGroupClient", "LEFT", "Line",
    "UNREACHABLE", "WITHHELD", "check_url", "is_start", "is_stop", "lines_from", "parse_voices",
]
