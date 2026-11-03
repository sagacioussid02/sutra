"""Reminders: a deterministic parser, a durable store, and a scheduler.

No model is involved in setting a reminder's time or in firing it: the
parser turns the user's words into a structured job once, and the
scheduler fires the job from the store. See
``openspec/changes/reminders-scheduler/``.
"""

from .db import ReminderSchemaError
from .parser import ParsedReminder, parse_request, reminder_request
from .scheduler import ReminderScheduler
from .service import ReminderService
from .store import InboxRow, ReminderRow, ReminderStore

__all__ = [
    "InboxRow",
    "ParsedReminder",
    "ReminderRow",
    "ReminderScheduler",
    "ReminderSchemaError",
    "ReminderService",
    "ReminderStore",
    "parse_request",
    "reminder_request",
]
