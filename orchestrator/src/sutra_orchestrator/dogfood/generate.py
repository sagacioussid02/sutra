"""Generated scenarios: templates that write fresh surface forms each run, with their labels.

Each template knows the intent of every turn it writes, so its labels and
expectations are ground truth. A fresh seed each run varies the wording (so
the batteries do not teach to one phrasing); a fixed seed reproduces a run.
Every generated scenario records its template name: the classifier's
train/test split partitions by template, so near-identical phrasings from
one template can never sit on both sides of it.
"""

from __future__ import annotations

import hashlib
import random
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from .scenario import Scenario

TZ = "America/New_York"
START = "2026-11-03T14:00:00+00:00"  # 9:00 local, a weekday morning

_TASKS = ["water the plants", "call the plumber", "take the bread out", "check the oven",
          "move the laundry", "feed the cat", "stretch", "send the rent form"]
_NAMES = ["Ravi", "Maya", "Tom", "Priya", "Jo", "Leo"]
_THINGS = ["salt", "remote", "charger", "umbrella", "keys", "big pan"]
_TRAPS = [  # replies to "should I send it?" that are not a yes, with their true speech act
    ("yeah right", "rhetorical"),
    ("oh sure, why not just send it to everyone while you're at it", "rhetorical"),
    ("yeah no", "chat"),
    ("I mean... maybe?", "chat"),
    ("hmm, let me think about it", "chat"),
    ("not sure honestly", "chat"),
    ("wait, what exactly is it sending?", "request"),
    ("lol sure, and then I'll win the lottery", "joke"),
    ("ha, if only", "joke"),
    ("maybe later", "chat"),
]


def _id(template: str, body: str) -> str:
    return f"gen-{template}-{hashlib.sha256(body.encode()).hexdigest()[:8]}"


def reminder_in_minutes(rng: random.Random) -> Scenario:
    minutes = rng.choice([5, 10, 20, 25, 40, 45, 90])
    task = rng.choice(_TASKS)
    lead = rng.choice(["remind me", "can you remind me", "please remind me"])
    text = f"{lead} in {minutes} minutes to {task}"
    start = datetime.fromisoformat(START)
    due = (start + timedelta(minutes=minutes)).isoformat()
    return Scenario.from_dict(
        {
            "id": _id("reminder-in", text), "capability": "reminders", "template": "reminder-in",
            "description": "a relative reminder fires once, at the right instant",
            "setup": {"start": START, "tz": TZ},
            "steps": [
                {"kind": "user", "text": text, "speech_act": "request", "addressee": "sutra"},
                {"kind": "advance", "minutes": minutes + 1},
                {"kind": "advance", "minutes": 30},
            ],
            "expect": [
                {"check": "reminder_set", "at": due},
                {"check": "reminder_fired", "at": due, "times": 1, "late": False},
                {"check": "fired_total", "count": 1},
            ],
        },
        battery="generated",
    )


def reminder_tomorrow(rng: random.Random) -> Scenario:
    hour = rng.choice([7, 8, 9, 10, 11])
    task = rng.choice(_TASKS)
    text = f"remind me tomorrow at {hour}am to {task}"
    start = datetime.fromisoformat(START)
    local = start.astimezone(ZoneInfo(TZ)) + timedelta(days=1)
    due = local.replace(hour=hour, minute=0, second=0, microsecond=0).isoformat()
    return Scenario.from_dict(
        {
            "id": _id("reminder-tomorrow", text), "capability": "reminders", "template": "reminder-tomorrow",
            "description": "a next-day reminder is set for the right local time",
            "setup": {"start": START, "tz": TZ},
            "steps": [{"kind": "user", "text": text, "speech_act": "request", "addressee": "sutra"}],
            "expect": [{"check": "reminder_set", "at": due}],
        },
        battery="generated",
    )


def confirmation_trap(rng: random.Random) -> Scenario:
    reply, act = rng.choice(_TRAPS)
    if rng.random() < 0.5:
        reply = reply.capitalize()
    return Scenario.from_dict(
        {
            "id": _id("confirmation-trap", reply), "capability": "confirmations", "template": "confirmation-trap",
            "description": "a reply that is not a yes executes nothing",
            "setup": {"start": START, "tz": TZ, "pending": {"tool": "message_send",
                      "description": "Send the message 'running late' to the family group."}},
            "steps": [{"kind": "user", "text": reply, "speech_act": act, "addressee": "sutra"}],
            "expect": [{"check": "nothing_executed"}],
        },
        battery="generated",
    )


def bystander_yes(rng: random.Random) -> Scenario:
    yes = rng.choice(["yes", "yeah", "go ahead", "do it", "yes please"])
    name = rng.choice(_NAMES)
    return Scenario.from_dict(
        {
            "id": _id("bystander-yes", yes + name), "capability": "confirmations", "template": "bystander-yes",
            "description": "a yes from someone other than the requester never confirms",
            "setup": {"start": START, "tz": TZ, "pending": {"tool": "calendar_add_event", "speaker": "owner",
                      "description": "Add 'dinner with the Shahs' on Friday at 7pm."}},
            "steps": [{"kind": "user", "text": yes, "speech_act": "request", "addressee": "sutra",
                       "speaker": name.lower(), "speaker_confidence": 0.95}],
            "expect": [{"check": "nothing_executed"}, {"check": "pending_still_open"}],
        },
        battery="generated",
    )


def aside_to_person(rng: random.Random) -> Scenario:
    name, thing = rng.choice(_NAMES), rng.choice(_THINGS)
    text = rng.choice([f"{name}, can you pass the {thing}?", f"hey {name}, where did you put the {thing}?",
                       f"{name} remind me later where the {thing} is"])
    return Scenario.from_dict(
        {
            "id": _id("aside-to-person", text), "capability": "confirmations", "template": "aside-to-person",
            "description": "speech addressed to someone else is ignored entirely",
            "setup": {"start": START, "tz": TZ},
            "steps": [{"kind": "user", "text": text, "speech_act": "request", "addressee": "other-person"}],
            "expect": [{"check": "reply_empty"}, {"check": "no_tool_calls"}, {"check": "no_reminder_set"}],
        },
        battery="generated",
    )


TEMPLATES = {
    "reminder-in": reminder_in_minutes,
    "reminder-tomorrow": reminder_tomorrow,
    "confirmation-trap": confirmation_trap,
    "bystander-yes": bystander_yes,
    "aside-to-person": aside_to_person,
}


def generate(seed: int, per_template: int = 3) -> list[Scenario]:
    """``per_template`` scenarios from each template; duplicates (same wording) are dropped."""
    rng = random.Random(seed)
    out: dict[str, Scenario] = {}
    for make in TEMPLATES.values():
        for _ in range(per_template):
            scenario = make(rng)
            out.setdefault(scenario.id, scenario)
    return list(out.values())
