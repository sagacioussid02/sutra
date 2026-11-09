"""The scenario format: turns, labels and expectations, all declared before a run.

A scenario is a script of steps. A ``user`` step is one utterance with its
intended ``speech_act`` and ``addressee`` labels; the other step kinds move
the fake clock or stop and start the reminder scheduler. ``expect`` lists the
deterministic checks the run must pass, and ``rubric`` names the soft
criteria (tone, offer timing, answer quality) a grader model may score.

Because the scenario author (or the template generator) wrote every turn,
the labels are ground truth, not a grader's opinion. That is what makes the
dataset this harness writes fit to train on.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

SPEECH_ACTS = ("request", "chat", "rhetorical", "joke", "aside")
ADDRESSEES = ("sutra", "other-person", "unclear")
CAPABILITIES = ("reminders", "confirmations", "answers", "memory", "offers", "drift")
STEP_KINDS = ("user", "advance", "scheduler_stop", "scheduler_start", "sweep", "new_session")
RUBRIC_CRITERIA = ("tone", "offer_timing", "answer_quality")


class ScenarioError(ValueError):
    """A scenario that cannot run as written."""


@dataclass(frozen=True)
class Step:
    kind: str
    text: str = ""
    speech_act: str = ""
    addressee: str = ""
    # Voice-layer turn context, for speaker-binding scenarios: who spoke and how sure.
    speaker: str | None = None
    speaker_confidence: float = 1.0
    minutes: float = 0.0  # for "advance"

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"kind": self.kind}
        if self.kind == "user":
            out.update(text=self.text, speech_act=self.speech_act, addressee=self.addressee)
            if self.speaker is not None:
                out.update(speaker=self.speaker, speaker_confidence=self.speaker_confidence)
        if self.kind == "advance":
            out["minutes"] = self.minutes
        return out

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Step":
        kind = data.get("kind", "user")
        if kind not in STEP_KINDS:
            raise ScenarioError(f"unknown step kind {kind!r}")
        step = cls(
            kind=kind,
            text=str(data.get("text", "")),
            speech_act=str(data.get("speech_act", "")),
            addressee=str(data.get("addressee", "")),
            speaker=data.get("speaker"),
            speaker_confidence=float(data.get("speaker_confidence", 1.0)),
            minutes=float(data.get("minutes", 0.0)),
        )
        if kind == "user":
            if not step.text.strip():
                raise ScenarioError("a user step needs text")
            if step.speech_act not in SPEECH_ACTS:
                raise ScenarioError(f"speech_act {step.speech_act!r} is not one of {SPEECH_ACTS}")
            if step.addressee not in ADDRESSEES:
                raise ScenarioError(f"addressee {step.addressee!r} is not one of {ADDRESSEES}")
        if kind == "advance" and step.minutes <= 0:
            raise ScenarioError("an advance step needs a positive number of minutes")
        return step


@dataclass(frozen=True)
class Check:
    name: str
    args: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"check": self.name, **self.args}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Check":
        data = dict(data)
        name = data.pop("check", None)
        if not name:
            raise ScenarioError("an expectation needs a 'check' name")
        return cls(name=str(name), args=data)


@dataclass(frozen=True)
class Scenario:
    id: str
    battery: str
    capability: str
    steps: tuple[Step, ...]
    expect: tuple[Check, ...]
    setup: dict[str, Any] = field(default_factory=dict)
    rubric: tuple[str, ...] = ()
    requires_live: bool = False  # needs the real model to mean anything
    template: str | None = None  # the template a generated scenario came from
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "id": self.id,
            "battery": self.battery,
            "capability": self.capability,
            "description": self.description,
            "setup": self.setup,
            "steps": [s.to_dict() for s in self.steps],
            "expect": [c.to_dict() for c in self.expect],
        }
        if self.rubric:
            out["rubric"] = list(self.rubric)
        if self.requires_live:
            out["requires_live"] = True
        if self.template:
            out["template"] = self.template
        return out

    @classmethod
    def from_dict(cls, data: dict[str, Any], *, battery: str | None = None) -> "Scenario":
        sid = str(data.get("id", "")).strip()
        if not sid:
            raise ScenarioError("a scenario needs an id")
        capability = data.get("capability", "")
        if capability not in CAPABILITIES:
            raise ScenarioError(f"{sid}: capability {capability!r} is not one of {CAPABILITIES}")
        steps = tuple(Step.from_dict(s) for s in data.get("steps", []))
        if not any(s.kind == "user" for s in steps):
            raise ScenarioError(f"{sid}: a scenario needs at least one user step")
        expect = tuple(Check.from_dict(c) for c in data.get("expect", []))
        if not expect:
            raise ScenarioError(f"{sid}: expectations are written before the run, and there are none")
        rubric = tuple(data.get("rubric", ()))
        for criterion in rubric:
            if criterion not in RUBRIC_CRITERIA:
                raise ScenarioError(f"{sid}: rubric criterion {criterion!r} is not one of {RUBRIC_CRITERIA}")
        return cls(
            id=sid,
            battery=battery or str(data.get("battery", "")),
            capability=capability,
            steps=steps,
            expect=expect,
            setup=dict(data.get("setup", {})),
            rubric=rubric,
            requires_live=bool(data.get("requires_live", False)),
            template=data.get("template"),
            description=str(data.get("description", "")),
        )

    @property
    def user_steps(self) -> list[Step]:
        return [s for s in self.steps if s.kind == "user"]

    def fingerprint(self) -> str:
        """A stable id for the scenario's content: same script, same fingerprint."""
        body = json.dumps(self.to_dict(), sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(body.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class Battery:
    name: str
    version: int
    scenarios: tuple[Scenario, ...]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Battery":
        name = str(data.get("battery", "")).strip()
        if not name:
            raise ScenarioError("a battery file needs a 'battery' name")
        version = int(data.get("version", 0))
        if version < 1:
            raise ScenarioError(f"battery {name}: version must be 1 or more")
        scenarios = tuple(Scenario.from_dict(s, battery=name) for s in data.get("scenarios", []))
        ids = [s.id for s in scenarios]
        if len(ids) != len(set(ids)):
            raise ScenarioError(f"battery {name}: scenario ids must be unique")
        return cls(name=name, version=version, scenarios=scenarios)
