"""Adaptive authentication: one-time questions from the user's own recent activity, behind a feature flipper.

See ``openspec/changes/adaptive-auth/``.
"""

from .commands import AuthCommands
from .db import AuthSchemaError
from .factory import build_auth
from .filters import usable
from .judge import MATCH, NO_MATCH, UNSURE, AnswerJudge
from .questions import Question, QuestionWriter, check
from .service import AuthReply, AuthService
from .store import AuthStore, Fact

__all__ = [
    "AnswerJudge", "AuthCommands", "AuthReply", "AuthSchemaError", "AuthService", "AuthStore", "Fact", "MATCH",
    "NO_MATCH", "Question", "build_auth", "QuestionWriter", "UNSURE", "check", "usable",
]
