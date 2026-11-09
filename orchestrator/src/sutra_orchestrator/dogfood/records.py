"""What a run leaves behind: the labelled dataset, the eval corpus, the scorecard, lesson proposals.

All of it lives under one directory (``orchestrator/evals/dogfood`` unless
configured otherwise), is synthetic by construction, and is safe to commit:

- ``dataset.jsonl`` + ``manifest.json``: every labelled user turn, once. A
  turn already in the dataset (same scenario fingerprint, same position,
  same text) is not added again, so a fixed battery adds its turns on the
  first run only and generated batteries add only new surface forms. The
  version bumps only when turns are added; training pins a version.
- ``corpus/``: every scenario that ever failed, copied verbatim. Corpus
  cases run on every later run and are never removed for passing.
- ``scorecard.jsonl``: one append-only line per run, per capability, with
  the deterministic and rubric tiers in separate fields.
- ``failures.jsonl``: one line per failed check, the history lesson
  proposals are drawn from.
- ``lesson_proposals.jsonl``: draft lessons in the self-learning format.
  Writing a proposal here changes nothing; the user imports it with
  ``dogfood import-lessons``, where it enters as ``proposed``.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .graders import BEHAVIOUR, ScenarioResult
from .scenario import ADDRESSEES, CAPABILITIES, SPEECH_ACTS, Scenario

DATASET = "dataset.jsonl"
MANIFEST = "manifest.json"
CORPUS = "corpus"
SCORECARD = "scorecard.jsonl"
FAILURES = "failures.jsonl"
PROPOSALS = "lesson_proposals.jsonl"

# Built-in markers of real personal data. Configured markers (names, places) are added to these.
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_LONG_DIGITS = re.compile(r"(?:\d[\s-]?){10,}")


class LintError(ValueError):
    """A turn that looks like real personal data."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _append_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    rows = list(rows)
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


# ---------------------------------------------------------------------- lint


def lint_text(text: str, markers: tuple[str, ...]) -> str | None:
    """The reason this text may not go in the dataset, or None if it is clean."""
    if _EMAIL.search(text):
        return "looks like an email address"
    if _LONG_DIGITS.search(text):
        return "looks like a phone, card or account number"
    low = text.lower()
    for marker in markers:
        if marker and marker.lower() in low:
            return "contains a configured personal marker"
    return None


# ---------------------------------------------------------------------- dataset


@dataclass(frozen=True)
class DatasetUpdate:
    version_before: int
    version_after: int
    added: int
    rejected: list[tuple[str, str]]  # (scenario id, reason)


def read_manifest(root: Path) -> dict[str, Any]:
    path = root / MANIFEST
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"dataset_version": 0, "turns": 0, "battery_versions": {}, "counts": {}, "checksum": ""}


def write_dataset(
    root: Path,
    results: list[ScenarioResult],
    *,
    run_id: str,
    battery_versions: dict[str, int],
    markers: tuple[str, ...],
) -> DatasetUpdate:
    path = root / DATASET
    existing = _read_jsonl(path)
    seen = {(r["scenario_fingerprint"], r["turn_index"], r["text"]) for r in existing}
    manifest = read_manifest(root)
    before = int(manifest.get("dataset_version", 0))
    rows: list[dict[str, Any]] = []
    rejected: list[tuple[str, str]] = []
    for result in results:
        if result.status != "graded":
            continue
        scenario = result.scenario
        fp = scenario.fingerprint()
        for index, step in enumerate(scenario.user_steps):
            key = (fp, index, step.text)
            if key in seen:
                continue
            reason = lint_text(step.text, markers)
            if reason is not None:
                rejected.append((scenario.id, reason))
                continue
            seen.add(key)
            rows.append(
                {
                    "dataset_version": before + 1,
                    "run_id": run_id,
                    "scenario_id": scenario.id,
                    "scenario_fingerprint": fp,
                    "battery": scenario.battery,
                    "template": scenario.template,
                    "capability": scenario.capability,
                    "turn_index": index,
                    "text": step.text,
                    "speech_act": step.speech_act,
                    "addressee": step.addressee,
                    "outcome": "pass" if result.passed else "fail",
                }
            )
    if not rows:
        return DatasetUpdate(before, before, 0, rejected)
    _append_jsonl(path, rows)
    all_rows = existing + rows
    versions = dict(manifest.get("battery_versions", {}))
    versions.update(battery_versions)
    manifest = {
        "dataset_version": before + 1,
        "turns": len(all_rows),
        "battery_versions": dict(sorted(versions.items())),
        "counts": {
            "speech_act": {k: sum(1 for r in all_rows if r["speech_act"] == k) for k in SPEECH_ACTS},
            "addressee": {k: sum(1 for r in all_rows if r["addressee"] == k) for k in ADDRESSEES},
        },
        "checksum": "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest(),
        "updated_at": _utc_now(),
        "note": "Synthetic turns only, written by the dogfood harness. Labels are the scenario author's intent.",
    }
    (root / MANIFEST).write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return DatasetUpdate(before, before + 1, len(rows), rejected)


# ---------------------------------------------------------------------- eval corpus


def corpus_path(root: Path, scenario: Scenario) -> Path:
    return root / CORPUS / f"{scenario.id}--{scenario.fingerprint()}.json"


def promote(root: Path, result: ScenarioResult, run_id: str) -> bool:
    """Copy a failed scenario into the corpus, verbatim. False if it is already there."""
    path = corpus_path(root, result.scenario)
    if path.exists():
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "promoted_in_run": run_id,
        "promoted_at": _utc_now(),
        "scenario": result.scenario.to_dict() | {"battery": result.scenario.battery},
        "failed_checks": [c.to_dict() for c in result.failures],
        "observed": result.observation.to_dict() if result.observation is not None else None,
    }
    path.write_text(json.dumps(record, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    return True


def load_corpus(root: Path) -> list[Scenario]:
    scenarios = []
    for path in sorted((root / CORPUS).glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))["scenario"]
        scenarios.append(Scenario.from_dict(data))
    return scenarios


# ---------------------------------------------------------------------- scorecard


def scorecard_line(
    results: list[ScenarioResult],
    *,
    run_id: str,
    mode: str,
    dataset_version: int,
    battery_versions: dict[str, int],
    grader_model: str | None,
    rubric_version: str | None,
) -> dict[str, Any]:
    caps: dict[str, dict[str, dict[str, int]]] = {}
    for cap in CAPABILITIES:
        tiers = {
            "deterministic": {"passed": 0, "failed": 0, "skipped": 0},
            "corpus": {"passed": 0, "failed": 0},
            "rubric": {"passed": 0, "failed": 0},
        }
        for r in results:
            if r.scenario.capability != cap:
                continue
            if r.status != "graded":
                if not r.from_corpus:
                    tiers["deterministic"]["skipped"] += 1
                continue
            tier = tiers["corpus"] if r.from_corpus else tiers["deterministic"]
            tier["passed" if r.passed else "failed"] += 1
            for v in r.rubric:
                tiers["rubric"]["passed" if v.passed else "failed"] += 1
        caps[cap] = tiers
    return {
        "run_id": run_id,
        "at": _utc_now(),
        "mode": mode,
        "dataset_version": dataset_version,
        "battery_versions": battery_versions,
        "grader_model": grader_model,
        "rubric_version": rubric_version,
        "critical_failures": [r.scenario.id for r in results if r.critical],
        "capabilities": caps,
        "evidence": "simulation" if mode == "scripted" else "simulation with the live model",
    }


def append_scorecard(root: Path, line: dict[str, Any]) -> None:
    _append_jsonl(root / SCORECARD, [line])


def render_scorecard(root: Path, last: int = 8) -> str:
    rows = _read_jsonl(root / SCORECARD)[-last:]
    if not rows:
        return "No runs yet."

    def cell(t: dict[str, int]) -> str:
        total = t["passed"] + t["failed"]
        return f"{t['passed']}/{total}" if total else "-"

    lines = [
        "Readiness scorecard (deterministic tier is the trend of record; simulation only, no living-room evidence)",
        "runs: " + ", ".join(f"{r['run_id']} ({r['mode']})" for r in rows),
    ]
    width = max(len(c) for c in CAPABILITIES)
    for cap in CAPABILITIES:
        det = " ".join(f"{cell(r['capabilities'][cap]['deterministic']):>5}" for r in rows)
        corpus = " ".join(f"{cell(r['capabilities'][cap]['corpus']):>5}" for r in rows)
        rubric = " ".join(f"{cell(r['capabilities'][cap]['rubric']):>5}" for r in rows)
        lines.append(f"{cap:<{width}}  checks {det}  | corpus {corpus}  | rubric {rubric}")
    critical = [sid for r in rows for sid in r.get("critical_failures", [])]
    if critical:
        lines.append("CRITICAL failures in these runs: " + ", ".join(sorted(set(critical))))
    return "\n".join(lines)


# ---------------------------------------------------------------------- failures and lessons


def record_failures(root: Path, results: list[ScenarioResult], run_id: str, mode: str) -> None:
    rows = []
    for r in results:
        for c in r.failures:
            rows.append(
                {
                    "run_id": run_id, "mode": mode, "scenario_id": r.scenario.id,
                    "template": r.scenario.template, "capability": r.scenario.capability,
                    "check": c.name, "shape": c.shape, "critical": c.critical,
                }
            )
    _append_jsonl(root / FAILURES, rows)


def propose_lessons(root: Path, threshold: int, run_id: str) -> list[dict[str, Any]]:
    """Draft lessons for behaviour-shaped failures that recur across ``threshold`` runs.

    The key is (check, template or scenario): the same expectation failing the same
    way. Bug-shaped failures never become lessons. Proposals already drafted are not
    drafted again.
    """
    from .graders import CHECKS

    history = _read_jsonl(root / FAILURES)
    runs: dict[tuple[str, str], set[str]] = defaultdict(set)
    scenarios: dict[tuple[str, str], set[str]] = defaultdict(set)
    for row in history:
        if row["shape"] != BEHAVIOUR:
            continue
        key = (row["check"], row.get("template") or row["scenario_id"])
        runs[key].add(row["run_id"])
        scenarios[key].add(row["scenario_id"])
    existing = {p["key"] for p in _read_jsonl(root / PROPOSALS)}
    new = []
    for key, run_ids in sorted(runs.items()):
        key_s = f"{key[0]}:{key[1]}"
        if len(run_ids) < threshold or key_s in existing:
            continue
        spec = CHECKS.get(key[0])
        new.append(
            {
                "key": key_s,
                "drafted_in_run": run_id,
                "drafted_at": _utc_now(),
                # The self-learning format: a guidance lesson, entering as "proposed".
                "text": spec.lesson if spec and spec.lesson else f"Do better on {key[1]}.",
                "effect": "guidance",
                "source": "outcomes",
                "origin": "dogfood",
                "status": "proposed",
                "reason": f"{key[0]} failed in {len(run_ids)} runs ({', '.join(sorted(scenarios[key]))})",
                "imported": False,
            }
        )
    _append_jsonl(root / PROPOSALS, new)
    return new


def import_lessons(root: Path, store: Any, now: datetime) -> list[int]:
    """Add drafted proposals to a lesson store as ``proposed``. Run by the user, never by a battery."""
    path = root / PROPOSALS
    rows = _read_jsonl(path)
    added = []
    for row in rows:
        if row.get("imported"):
            continue
        # The lesson store knows two sources; a battery's repeated failure is a lesson from outcomes.
        # The proposals file keeps the dogfood provenance (key, reason, run) for the record.
        added.append(store.add(row["text"], row.get("effect", "guidance"), "outcomes", now))
        row["imported"] = True
    if added:
        path.write_text("".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in rows), encoding="utf-8")
    return added
