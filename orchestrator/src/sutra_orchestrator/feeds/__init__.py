"""Curiosity feeds: weather alerts, topic news, and a morning brief, all opt-in.

See ``openspec/changes/curiosity-feeds/``.
"""

from .commands import FeedCommands
from .factory import build_feeds
from .service import BRIEF_TOOL, NEWS_SOURCE, WEATHER_SOURCE, FeedService

__all__ = ["BRIEF_TOOL", "FeedCommands", "FeedService", "NEWS_SOURCE", "WEATHER_SOURCE", "build_feeds"]
