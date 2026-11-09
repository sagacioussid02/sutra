"""Explicit, scoped enrolment of speakers.

Enrolment is a flow, not a side effect: it starts only from a deliberate
command, records a small number of short samples, and stores the resulting
profile locally with owner-only permissions, under a user-chosen label
mapped to a ``per-user-identity`` user id. Nobody is enrolled by being
overheard — hearing an unenrolled voice in conversation creates nothing —
and a profile is never included in model prompts: this store has no path
into any prompt, and the only readers are the control surface
(list/delete) and a future identification implementation.

The default scope is the owner. Enrolling anyone else is one deliberate
act per person, by the user. Deleting a profile removes its samples and
its registry entry, and takes effect on the next utterance.
"""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

MAX_SAMPLES = 5
MAX_SAMPLE_BYTES = 1_000_000  # ~1 MB per short sample


@dataclass(frozen=True)
class SpeakerProfile:
    """One enrolled speaker: label, user id, and how many samples were kept."""

    label: str
    user_id: str
    samples: int
    created_at: str


@dataclass
class _PendingEnrolment:
    label: str
    user_id: str
    samples: list[bytes] = field(default_factory=list)


def _check_label(label: str) -> str:
    label = label.strip()
    if not label or label in (".", "..") or "/" in label or "\\" in label:
        raise ValueError(f"not a usable speaker label: {label!r}")
    return label


class EnrolmentStore:
    """Local, owner-only enrolment profiles and their voice samples."""

    def __init__(self, directory: str | Path) -> None:
        self._dir = Path(directory).expanduser()
        self._dir.mkdir(parents=True, exist_ok=True)
        os.chmod(self._dir, 0o700)
        self._registry_path = self._dir / "speakers.json"
        self._samples_dir = self._dir / "samples"
        self._samples_dir.mkdir(exist_ok=True)
        os.chmod(self._samples_dir, 0o700)
        self._registry: dict[str, dict] = self._load()
        self._pending: _PendingEnrolment | None = None

    # ------------------------------------------------------------- registry

    def _load(self) -> dict[str, dict]:
        if not self._registry_path.exists():
            return {}
        try:
            data = json.loads(self._registry_path.read_text())
        except (json.JSONDecodeError, OSError) as exc:
            raise ValueError(f"enrolment registry is unreadable: {self._registry_path}") from exc
        if not isinstance(data, dict):
            raise ValueError(f"enrolment registry is not an object: {self._registry_path}")
        return data

    def _save(self) -> None:
        tmp = self._registry_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._registry, indent=2, sort_keys=True))
        os.chmod(tmp, 0o600)
        os.replace(tmp, self._registry_path)

    # ------------------------------------------------------------- enrolment flow

    def start_enrolment(self, label: str, user_id: str) -> None:
        """Begin a deliberate enrolment. Raises if one is already running or the label exists."""
        label = _check_label(label)
        if self._pending is not None:
            raise ValueError(f"enrolment already in progress for {self._pending.label!r}")
        if label in self._registry:
            raise ValueError(f"speaker {label!r} is already enrolled; delete it first to re-enrol")
        if not user_id.strip():
            raise ValueError("an enrolled speaker needs a user id")
        self._pending = _PendingEnrolment(label=label, user_id=user_id.strip())

    def add_sample(self, wav: bytes) -> int:
        """Record one short sample for the enrolment in progress. Returns the sample count."""
        if self._pending is None:
            raise ValueError("no enrolment in progress; start one before recording samples")
        if len(self._pending.samples) >= MAX_SAMPLES:
            raise ValueError(f"enrolment takes at most {MAX_SAMPLES} samples")
        if not wav:
            raise ValueError("an enrolment sample must not be empty")
        if len(wav) > MAX_SAMPLE_BYTES:
            raise ValueError(f"an enrolment sample must be under {MAX_SAMPLE_BYTES} bytes")
        self._pending.samples.append(bytes(wav))
        return len(self._pending.samples)

    def finish_enrolment(self) -> SpeakerProfile:
        """Store the profile and its samples. Raises unless at least one sample was recorded."""
        if self._pending is None:
            raise ValueError("no enrolment in progress")
        pending, self._pending = self._pending, None
        if not pending.samples:
            raise ValueError("enrolment needs at least one sample")
        label_dir = self._samples_dir / pending.label
        label_dir.mkdir(exist_ok=True)
        os.chmod(label_dir, 0o700)
        for i, wav in enumerate(pending.samples, 1):
            path = label_dir / f"sample-{i}.wav"
            path.write_bytes(wav)
            os.chmod(path, 0o600)
        profile = SpeakerProfile(
            label=pending.label,
            user_id=pending.user_id,
            samples=len(pending.samples),
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        self._registry[pending.label] = {
            "user_id": profile.user_id,
            "samples": profile.samples,
            "created_at": profile.created_at,
        }
        self._save()
        return profile

    def cancel_enrolment(self) -> None:
        """Drop the enrolment in progress; nothing is stored."""
        self._pending = None

    @property
    def enrolment_in_progress(self) -> str | None:
        """The label being enrolled right now, or None."""
        return self._pending.label if self._pending is not None else None

    # ------------------------------------------------------------- control surface

    def list_profiles(self) -> list[SpeakerProfile]:
        """Every enrolled speaker, by label."""
        return [
            SpeakerProfile(label=label, user_id=entry["user_id"], samples=entry["samples"], created_at=entry["created_at"])
            for label, entry in sorted(self._registry.items())
        ]

    def is_enrolled(self, label: str) -> bool:
        return label in self._registry

    def user_id_for(self, label: str) -> str | None:
        entry = self._registry.get(label)
        return entry["user_id"] if entry is not None else None

    def delete(self, label: str) -> bool:
        """Delete a profile and its samples. Takes effect on the next utterance.

        Returns True when a profile existed. Deleting is the only way a
        profile goes away; nothing in the conversation path can do it.
        """
        label = _check_label(label)
        if label not in self._registry:
            return False
        del self._registry[label]
        self._save()
        shutil.rmtree(self._samples_dir / label, ignore_errors=True)
        return True
