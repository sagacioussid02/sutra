"""Event kinds and the envelope: the registry mirrors the gateway's ``kinds.json``."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from ..errors import OrchestratorError

MAX_PAYLOAD_BYTES = 1024
URGENCIES = ("low", "medium", "high")


class EventError(OrchestratorError):
    """An event the log refuses."""


def _kind(minutes: int) -> dict[str, Any]:
    return {
        "default_expiry_minutes": minutes,
        "fields": {
            "summary": {"required": True, "max": 200},
            "urgency": {"enum": list(URGENCIES)},
            "ref": {"max": 120},
        },
    }


# One entry per kind. Kept identical to gateway/internal/events/kinds.json (a test enforces it).
KINDS: dict[str, dict[str, Any]] = {
    "weather_warning": _kind(360),
    "calendar_change": _kind(1440),
    "camera_motion": _kind(30),
    "broker_fill": _kind(120),
    "phone_notification": _kind(240),
}


@dataclass(frozen=True)
class Event:
    id: str
    source: str
    kind: str
    occurred_at: datetime
    received_at: datetime
    user_id: str
    payload: dict[str, str]
    idempotency_key: str
    expires_at: datetime
    seq: int = 0


def _when(value: Any, name: str) -> datetime:
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise EventError(f"{name} is not a timestamp") from exc
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def validate_payload(kind: str, payload: Any) -> dict[str, str]:
    spec = KINDS.get(kind)
    if spec is None:
        raise EventError(f"unknown event kind {kind!r}")
    if not isinstance(payload, dict):
        raise EventError("payload must be an object")
    fields = spec["fields"]
    size = 0
    for name, value in payload.items():
        f = fields.get(name)
        if f is None:
            raise EventError(f"unknown payload field {name!r}")
        if not isinstance(value, str):
            raise EventError(f"payload field {name!r} must be text")
        if f.get("max") and len(value) > f["max"]:
            raise EventError(f"payload field {name!r} is too long")
        if f.get("enum") and value not in f["enum"]:
            raise EventError(f"payload field {name!r} must be one of {f['enum']}")
        size += len(name) + len(value.encode())
    if size > MAX_PAYLOAD_BYTES:
        raise EventError("payload is too large")
    for name, f in fields.items():
        if f.get("required") and not payload.get(name, "").strip():
            raise EventError(f"payload field {name!r} is required")
    return dict(payload)


def parse_envelope(data: Any, now: datetime) -> Event:
    """Validate a forwarded envelope again: the orchestrator does not trust the wire."""
    if not isinstance(data, dict):
        raise EventError("envelope must be an object")
    for key in ("id", "source", "kind", "user_id", "received_at", "expires_at", "payload"):
        if not data.get(key):
            raise EventError(f"envelope is missing {key}")
    kind = str(data["kind"])
    payload = validate_payload(kind, data["payload"])
    received = _when(data["received_at"], "received_at")
    expires = _when(data["expires_at"], "expires_at")
    if expires - received > timedelta(minutes=KINDS[kind]["default_expiry_minutes"]):
        raise EventError("expiry is longer than the kind allows")
    return Event(
        id=str(data["id"])[:64], source=str(data["source"])[:64], kind=kind,
        occurred_at=_when(data.get("occurred_at") or data["received_at"], "occurred_at"),
        received_at=received, user_id=str(data["user_id"])[:64], payload=payload,
        idempotency_key=str(data.get("idempotency_key") or "")[:80], expires_at=expires,
    )
