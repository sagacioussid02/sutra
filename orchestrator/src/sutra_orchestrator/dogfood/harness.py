"""One battery run, start to finish: guard, run, grade, record, report."""

from __future__ import annotations

import json
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import records
from .generate import generate
from .graders import RUBRIC_VERSION, ScenarioResult, grade, rubric_grade, validate
from .profile import Profile, guard
from .runner import run_scenario
from .scenario import CAPABILITIES, Battery, Scenario
from .stubs import BudgetedModel

BATTERIES = "batteries"
GENERATED_VERSION = 1  # bump when a template's wording or expectations change


class BatteriesError(ValueError):
    """A run was asked to grade without the fixed batteries it exists to run."""


@dataclass
class RunOptions:
    out_dir: Path
    mode: str = "scripted"  # "scripted" (free, deterministic) or "live" (the real model)
    batteries: tuple[str, ...] = ()  # empty: every battery
    seed: int | None = None  # None: a fresh seed, recorded in the report
    per_template: int = 3
    include_corpus: bool = True
    rubric: bool = False
    grader_model: str = ""
    lesson_runs: int = 3
    personal_markers: tuple[str, ...] = ()
    write: bool = True  # False: run and report, write nothing


@dataclass
class RunReport:
    run_id: str
    mode: str
    seed: int
    results: list[ScenarioResult]
    battery_versions: dict[str, int]
    battery_counts: dict[str, int] = field(default_factory=dict)
    dataset: records.DatasetUpdate | None = None
    promoted: list[str] = field(default_factory=list)
    lessons: list[dict[str, Any]] = field(default_factory=list)
    model_calls: int = 0
    budget: int = 0

    @property
    def ok(self) -> bool:
        return all(r.passed for r in self.results if r.status == "graded")

    def text(self) -> str:
        graded = [r for r in self.results if r.status == "graded"]
        failed = [r for r in graded if not r.passed]
        skipped = [r for r in self.results if r.status == "skipped"]
        not_run = [r for r in self.results if r.status == "not_run"]
        lines = [f"Dogfood run {self.run_id} ({self.mode}, seed {self.seed})"]
        if self.battery_counts:
            loaded = ", ".join(f"{name} ({count})" for name, count in self.battery_counts.items())
            lines.append(f"  batteries: {loaded}")
        else:
            lines.append("  WARNING: no fixed batteries loaded; only generated scenarios and the eval corpus ran.")
        for cap in CAPABILITIES:
            mine = [r for r in graded if r.scenario.capability == cap]
            if mine:
                passed = sum(1 for r in mine if r.passed)
                lines.append(f"  {cap}: {passed}/{len(mine)} passed")
        if not failed:
            lines.append(f"All {len(graded)} graded scenarios passed.")
        for r in failed:
            tag = "CRITICAL " if r.critical else ""
            where = " (corpus)" if r.from_corpus else ""
            for c in r.failures:
                lines.append(f"  {tag}FAIL {r.scenario.id}{where} [{c.shape}] {c.name}: {c.detail}")
        bugs = sorted({r.scenario.id for r in failed if any(c.shape == "bug" for c in r.failures)})
        if bugs:
            lines.append("Bug-shaped failures, for a normal fix PR (not lessons): " + ", ".join(bugs))
        if skipped:
            lines.append(f"{len(skipped)} scenario(s) skipped: {skipped[0].reason}")
        if not_run:
            lines.append(f"{len(not_run)} scenario(s) not run: {not_run[0].reason}")
        for r in graded:
            for v in r.rubric:
                if not v.passed:
                    lines.append(f"  rubric (advisory) {r.scenario.id} {v.criterion}: {v.rationale}")
        if self.promoted:
            lines.append("New eval corpus cases: " + ", ".join(self.promoted))
        if self.lessons:
            lines.append(f"{len(self.lessons)} draft lesson proposal(s); import with `dogfood import-lessons`.")
        if self.dataset is not None:
            d = self.dataset
            lines.append(f"Dataset v{d.version_before} -> v{d.version_after} (+{d.added} turns)")
            for sid, reason in d.rejected:
                lines.append(f"  lint rejected a turn of {sid}: {reason}")
        if self.mode == "live":
            lines.append(f"Model calls: {self.model_calls} of a budget of {self.budget}")
        return "\n".join(lines)


def load_batteries(root: Path, names: tuple[str, ...] = ()) -> list[Battery]:
    batteries = []
    for path in sorted((root / BATTERIES).glob("*.json")):
        battery = Battery.from_dict(json.loads(path.read_text(encoding="utf-8")))
        if names and battery.name not in names:
            continue
        batteries.append(battery)
    missing = set(names) - {b.name for b in batteries} - {"generated"}
    if missing:
        raise ValueError(f"no battery named {', '.join(sorted(missing))}")
    return batteries


def _no_batteries_message(out_dir: Path) -> str:
    batteries_dir = out_dir / BATTERIES
    state = "does not exist" if not batteries_dir.is_dir() else "contains no battery files"
    return (
        f"no fixed batteries loaded: {batteries_dir} {state}. A run needs the fixed battery "
        "JSON files (reminders, confirmations, offers, ...) in a "
        f"'{BATTERIES}' directory under the dogfood output directory; without them it would "
        "grade only generated scenarios and report a misleading pass. "
        f"Check SUTRA_DOGFOOD_DIR (the output directory in use is {out_dir})."
    )


def _run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + secrets.token_hex(2)


async def run(options: RunOptions, profile: Profile, model: Any, *, budget: int = 0) -> RunReport:
    # The guard runs before anything else: no scenario is even loaded against a non-sandbox profile.
    guard(profile)
    seed = options.seed if options.seed is not None else secrets.randbelow(2**31)
    batteries = load_batteries(options.out_dir, options.batteries)
    planned: list[tuple[Scenario, bool]] = [(s, False) for b in batteries for s in b.scenarios]
    versions = {b.name: b.version for b in batteries}
    if not options.batteries or "generated" in options.batteries:
        planned += [(s, False) for s in generate(seed, options.per_template)]
        versions["generated"] = GENERATED_VERSION
    corpus: list[Scenario] = []
    if options.include_corpus:
        ran = {s.fingerprint() for s, _ in planned}
        corpus = [s for s in records.load_corpus(options.out_dir) if s.fingerprint() not in ran]
    if not batteries and not options.batteries and not corpus:
        # No fixed batteries and no promoted corpus cases either: the run would grade
        # only generated templates and still report a pass. Refuse, loudly -- a fresh
        # or misconfigured output directory must never look like a green run.
        raise BatteriesError(_no_batteries_message(options.out_dir))
    planned += [(s, True) for s in corpus]
    for scenario, _ in planned:
        validate(scenario)

    counted = BudgetedModel(model, budget) if options.mode == "live" else model
    results: list[ScenarioResult] = []
    for scenario, from_corpus in planned:
        if scenario.requires_live and options.mode != "live":
            results.append(ScenarioResult(scenario, "skipped", reason="needs the live model", from_corpus=from_corpus))
            continue
        if options.mode == "live" and counted.calls >= budget:
            results.append(ScenarioResult(scenario, "not_run", reason="the model-call budget was spent", from_corpus=from_corpus))
            continue
        refused_before = getattr(counted, "refused", 0)
        obs = await run_scenario(scenario, profile, counted)
        if getattr(counted, "refused", 0) > refused_before:
            # The budget ran out mid-conversation: what happened is not the assistant's behaviour.
            results.append(ScenarioResult(scenario, "not_run", reason="the model-call budget was spent", from_corpus=from_corpus))
            continue
        result = ScenarioResult(scenario, "graded", grade(scenario, obs), observation=obs, from_corpus=from_corpus)
        if options.rubric and scenario.rubric and options.mode == "live":
            result.rubric = await rubric_grade(scenario, obs, counted, options.grader_model)
        results.append(result)

    report = RunReport(
        run_id=_run_id(), mode=options.mode, seed=seed, results=results, battery_versions=versions,
        battery_counts={b.name: len(b.scenarios) for b in batteries},
        model_calls=getattr(counted, "calls", 0), budget=budget,
    )
    if options.write:
        _record(options, report)
    return report


def _record(options: RunOptions, report: RunReport) -> None:
    root = options.out_dir
    report.dataset = records.write_dataset(
        root, report.results, run_id=report.run_id, battery_versions=report.battery_versions,
        markers=options.personal_markers,
    )
    for r in report.results:
        if r.status == "graded" and not r.passed and records.promote(root, r, report.run_id):
            report.promoted.append(r.scenario.id)
    records.record_failures(root, report.results, report.run_id, report.mode)
    report.lessons = records.propose_lessons(root, options.lesson_runs, report.run_id)
    rubric_used = options.rubric and options.mode == "live"
    records.append_scorecard(
        root,
        records.scorecard_line(
            report.results, run_id=report.run_id, mode=report.mode,
            dataset_version=report.dataset.version_after, battery_versions=report.battery_versions,
            grader_model=options.grader_model if rubric_used else None,
            rubric_version=RUBRIC_VERSION if rubric_used else None,
        ),
    )
