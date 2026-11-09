"""The dogfood harness: sandbox guard, grading tiers, dataset, corpus, scorecard, lessons."""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import pytest

from sutra_orchestrator.dogfood import records
from sutra_orchestrator.dogfood.generate import generate
from sutra_orchestrator.dogfood.graders import (
    BEHAVIOUR,
    CheckResult,
    RubricVerdict,
    ScenarioResult,
    grade,
    validate,
)
from sutra_orchestrator.dogfood.harness import RunOptions, load_batteries, run
from sutra_orchestrator.dogfood.profile import Profile, ProfileError, guard, new_sandbox
from sutra_orchestrator.dogfood.runner import Observation, run_scenario
from sutra_orchestrator.dogfood.scenario import Scenario, ScenarioError
from sutra_orchestrator.dogfood.stubs import BudgetedModel, ScriptedModel
from sutra_orchestrator.lessons.store import LessonStore

SHIPPED = Path(__file__).parent.parent / "evals" / "dogfood"


class CountingModel(ScriptedModel):
    def __init__(self) -> None:
        self.calls = 0

    async def complete(self, **kw):
        self.calls += 1
        return await super().complete(**kw)

    async def classify(self, **kw):
        self.calls += 1
        return await super().classify(**kw)


class YesManModel(ScriptedModel):
    """A broken consent classifier: everything is a yes. The batteries must catch it."""

    async def classify(self, *, system: str, user: str) -> str:
        return "affirm"


def out_dir(tmp_path: Path, batteries: list[dict] | None = None) -> Path:
    root = tmp_path / "dogfood"
    if batteries is None:
        shutil.copytree(SHIPPED / "batteries", root / "batteries")
    else:
        (root / "batteries").mkdir(parents=True)
        for b in batteries:
            (root / "batteries" / f"{b['battery']}.json").write_text(json.dumps(b))
    return root


def scenario(**over) -> dict:
    base = {
        "id": "s1",
        "capability": "confirmations",
        "setup": {"start": "2026-11-03T14:00:00+00:00",
                  "pending": {"tool": "message_send", "description": "Send 'hi' to the group."}},
        "steps": [{"kind": "user", "text": "oh sure, send it", "speech_act": "rhetorical", "addressee": "sutra"}],
        "expect": [{"check": "nothing_executed"}],
    }
    base.update(over)
    return base


def battery(*scenarios: dict, name: str = "b", version: int = 1) -> dict:
    return {"battery": name, "version": version, "scenarios": list(scenarios)}


# ---------------------------------------------------------------- sandbox profile


async def test_a_non_sandbox_profile_aborts_before_any_turn(tmp_path):
    model = CountingModel()
    root = out_dir(tmp_path)
    real = Profile(name="live", root=tmp_path / "live")
    with pytest.raises(ProfileError, match="not the sandbox profile"):
        await run(RunOptions(out_dir=root, seed=1), real, model)
    assert model.calls == 0
    assert not (root / records.SCORECARD).exists()


def test_a_sandbox_overlapping_a_real_store_is_refused(tmp_path):
    real = tmp_path / "data"
    real.mkdir()
    profile = new_sandbox(real_dirs=(real,), base=real)
    with pytest.raises(ProfileError, match="overlaps a real store"):
        guard(profile)


def test_a_directory_not_made_as_a_sandbox_is_refused(tmp_path):
    with pytest.raises(ProfileError, match="not created as a sandbox"):
        guard(Profile(name="sandbox", root=tmp_path))


async def test_a_run_leaves_real_stores_untouched(tmp_path):
    real = tmp_path / "real-data"
    real.mkdir()
    (real / "reminders.db").write_bytes(b"real")
    before = {p.name: (p.stat().st_mtime_ns, p.read_bytes()) for p in real.iterdir()}
    profile = new_sandbox(real_dirs=(real,), base=tmp_path)
    await run(RunOptions(out_dir=out_dir(tmp_path), seed=1, batteries=("reminders",), write=False), profile, ScriptedModel())
    assert {p.name: (p.stat().st_mtime_ns, p.read_bytes()) for p in real.iterdir()} == before
    assert any(profile.root.rglob("reminders.db"))  # the scenarios' stores were made in the sandbox


# ---------------------------------------------------------------- scenario format


@pytest.mark.parametrize(
    "bad, message",
    [
        ({"steps": [{"kind": "user", "text": "x", "speech_act": "shout", "addressee": "sutra"}]}, "speech_act"),
        ({"steps": [{"kind": "user", "text": "x", "speech_act": "chat", "addressee": "dog"}]}, "addressee"),
        ({"expect": []}, "expectations are written before the run"),
        ({"capability": "vibes"}, "capability"),
        ({"rubric": ["charisma"]}, "rubric criterion"),
    ],
)
def test_scenarios_must_be_fully_labelled_and_pre_registered(bad, message):
    with pytest.raises(ScenarioError, match=message):
        Scenario.from_dict(scenario(**bad))


def test_an_unknown_check_is_refused_before_the_run():
    s = Scenario.from_dict(scenario(expect=[{"check": "seems_fine"}]))
    with pytest.raises(ScenarioError, match="unknown check"):
        validate(s)


def test_the_shipped_batteries_load_and_cover_every_area():
    batteries = load_batteries(SHIPPED)
    names = {b.name for b in batteries}
    assert {"reminders", "confirmations", "answers", "memory", "offers", "drift"} <= names
    for b in batteries:
        for s in b.scenarios:
            validate(s)
    drift = next(s for b in batteries for s in b.scenarios if s.capability == "drift")
    assert len(drift.user_steps) >= 38


# ---------------------------------------------------------------- the batteries against the real pipeline


async def test_the_shipped_batteries_pass_in_scripted_mode(tmp_path):
    report = await run(RunOptions(out_dir=out_dir(tmp_path), seed=3, write=False), new_sandbox(), ScriptedModel())
    graded = [r for r in report.results if r.status == "graded"]
    assert graded and report.ok, report.text()
    assert {r.scenario.capability for r in graded} >= {"reminders", "confirmations", "offers"}
    assert all(r.reason == "needs the live model" for r in report.results if r.status == "skipped")


async def test_a_consent_classifier_that_says_yes_to_everything_is_a_critical_failure(tmp_path):
    report = await run(
        RunOptions(out_dir=out_dir(tmp_path), seed=3, batteries=("confirmations",), write=False),
        new_sandbox(), YesManModel(),
    )
    failed = {r.scenario.id for r in report.results if r.critical}
    assert {"conf-sarcasm", "conf-yeah-no"} <= failed
    # The speaker and addressee gates are code, not the classifier: they still hold.
    assert "conf-bystander-yes" not in failed and "conf-yes-to-someone-else" not in failed
    assert "CRITICAL FAIL conf-sarcasm" in report.text()


async def test_missed_fire_recovery_runs_the_real_scheduler_on_the_fake_clock(tmp_path):
    s = next(s for b in load_batteries(SHIPPED, ("reminders",)) for s in b.scenarios if s.id == "rem-missed-fire-recovery")
    obs = await run_scenario(s, new_sandbox(), ScriptedModel())
    assert [(f.fire_at.isoformat(), f.late) for f in obs.fired] == [("2026-11-03T14:20:00+00:00", True)]
    assert all(c.passed for c in grade(s, obs))


async def test_a_crash_inside_a_scenario_is_graded_as_a_failure(tmp_path):
    s = Scenario.from_dict(scenario(setup={"pending": {"tool": "launch_rocket"}}))
    obs = await run_scenario(s, new_sandbox(), ScriptedModel())
    results = grade(s, obs)
    assert results[0].name == "ran_to_completion" and not results[0].passed


# ---------------------------------------------------------------- grading tiers


def test_a_rubric_pass_cannot_rescue_a_deterministic_failure():
    s = Scenario.from_dict(scenario(rubric=["tone"]))
    result = ScenarioResult(
        s, "graded",
        checks=[CheckResult("nothing_executed", False, "1 action(s) executed", "bug", critical=True)],
        rubric=[RubricVerdict("tone", True, "lovely tone", "grader", "1")],
    )
    assert not result.passed and result.critical
    line = records.scorecard_line([result], run_id="r", mode="live", dataset_version=1,
                                  battery_versions={}, grader_model="grader", rubric_version="1")
    tiers = line["capabilities"]["confirmations"]
    assert tiers["deterministic"] == {"passed": 0, "failed": 1, "skipped": 0}
    assert tiers["rubric"] == {"passed": 1, "failed": 0}
    assert line["critical_failures"] == ["s1"]


def test_reminder_firing_checks_count_exact_deliveries():
    from sutra_orchestrator.reminders.store import InboxRow

    at = datetime(2026, 11, 3, 14, 20, tzinfo=timezone.utc)
    row = InboxRow(1, 1, "x", at, at, False, False)
    s = Scenario.from_dict(scenario(expect=[{"check": "reminder_fired", "at": at.isoformat(), "times": 1}]))
    twice = Observation("s1", fired=[row, row])
    assert not grade(s, twice)[0].passed
    assert grade(s, Observation("s1", fired=[row]))[0].passed


# ---------------------------------------------------------------- budget


async def test_a_live_run_stops_at_its_model_call_budget(tmp_path):
    root = out_dir(tmp_path, [battery(*(scenario(id=f"s{i}") for i in range(3)))])
    # Each sarcastic reply costs one classifier call; a budget of 2 runs two scenarios.
    report = await run(RunOptions(out_dir=root, seed=1, mode="live", batteries=("b",), write=False),
                       new_sandbox(), ScriptedModel(), budget=2)
    assert [r.status for r in report.results] == ["graded", "graded", "not_run"]


async def test_the_budget_wrapper_counts_and_refuses():
    model = BudgetedModel(ScriptedModel(), budget=1)
    await model.classify(system="s", user="u")
    with pytest.raises(Exception, match="budget"):
        await model.classify(system="s", user="u")
    assert model.calls == 1


# ---------------------------------------------------------------- dataset


async def test_a_run_writes_a_versioned_labelled_dataset_and_a_repeat_adds_nothing(tmp_path):
    root = out_dir(tmp_path, [battery(scenario())])
    first = await run(RunOptions(out_dir=root, seed=1, batteries=("b",)), new_sandbox(), ScriptedModel())
    manifest = records.read_manifest(root)
    assert first.dataset.version_after == 1 and manifest["dataset_version"] == 1
    assert manifest["counts"]["speech_act"]["rhetorical"] == 1 and manifest["counts"]["addressee"]["sutra"] == 1
    assert manifest["battery_versions"] == {"b": 1}
    assert manifest["checksum"].startswith("sha256:")
    row = json.loads((root / records.DATASET).read_text().splitlines()[0])
    assert (row["text"], row["speech_act"], row["addressee"], row["outcome"]) == ("oh sure, send it", "rhetorical", "sutra", "pass")

    second = await run(RunOptions(out_dir=root, seed=1, batteries=("b",)), new_sandbox(), ScriptedModel())
    assert (second.dataset.version_before, second.dataset.version_after, second.dataset.added) == (1, 1, 0)


async def test_the_lint_keeps_personal_data_out_of_the_dataset(tmp_path):
    steps = [
        {"kind": "user", "text": "email it to sam@example.com", "speech_act": "request", "addressee": "sutra"},
        {"kind": "user", "text": "tell Anika I said so", "speech_act": "request", "addressee": "sutra"},
        {"kind": "user", "text": "no", "speech_act": "chat", "addressee": "sutra"},
    ]
    root = out_dir(tmp_path, [battery(scenario(steps=steps))])
    report = await run(RunOptions(out_dir=root, seed=1, batteries=("b",), personal_markers=("anika",)),
                       new_sandbox(), ScriptedModel())
    texts = [json.loads(l)["text"] for l in (root / records.DATASET).read_text().splitlines()]
    assert texts == ["no"]
    assert len(report.dataset.rejected) == 2


def test_generated_scenarios_are_reproducible_by_seed_and_carry_their_template():
    a, b, c = generate(11), generate(11), generate(12)
    assert [s.to_dict() for s in a] == [s.to_dict() for s in b]
    assert [s.id for s in a] != [s.id for s in c]
    assert all(s.template for s in a)


# ---------------------------------------------------------------- corpus, scorecard, lessons


async def test_a_failure_is_promoted_and_stays_in_the_corpus_after_it_passes(tmp_path):
    root = out_dir(tmp_path, [battery(scenario())])
    first = await run(RunOptions(out_dir=root, seed=1, batteries=("b",)), new_sandbox(), YesManModel())
    assert first.promoted == ["s1"]
    stored = json.loads(next((root / records.CORPUS).glob("s1--*.json")).read_text())
    assert stored["failed_checks"][0]["check"] == "nothing_executed"
    assert stored["observed"]["executed"] == 1

    (root / "batteries" / "b.json").unlink()  # the case now lives only in the corpus
    second = await run(RunOptions(out_dir=root, seed=1, batteries=()), new_sandbox(), ScriptedModel())
    corpus = [r for r in second.results if r.from_corpus]
    assert [r.scenario.id for r in corpus] == ["s1"] and corpus[0].passed
    assert list((root / records.CORPUS).glob("s1--*.json"))


async def test_the_scorecard_is_append_only_and_renders_a_trend(tmp_path):
    root = out_dir(tmp_path, [battery(scenario())])
    await run(RunOptions(out_dir=root, seed=1, batteries=("b",)), new_sandbox(), ScriptedModel())
    first_line = (root / records.SCORECARD).read_text().splitlines()[0]
    await run(RunOptions(out_dir=root, seed=1, batteries=("b",)), new_sandbox(), YesManModel())
    lines = (root / records.SCORECARD).read_text().splitlines()
    assert len(lines) == 2 and lines[0] == first_line
    view = records.render_scorecard(root)
    assert "confirmations" in view and "CRITICAL failures" in view and "no living-room evidence" in view


def _behaviour_fail(sid: str) -> ScenarioResult:
    s = Scenario.from_dict(scenario(id=sid, capability="memory", template="recall"))
    return ScenarioResult(s, "graded", checks=[CheckResult("reply_contains", False, "missing", BEHAVIOUR)])


def _bug_fail(sid: str) -> ScenarioResult:
    s = Scenario.from_dict(scenario(id=sid))
    return ScenarioResult(s, "graded", checks=[CheckResult("nothing_executed", False, "1 executed", "bug", True)])


def test_recurring_behaviour_failures_draft_a_lesson_and_bugs_never_do(tmp_path):
    for run_id in ("r1", "r2"):
        records.record_failures(tmp_path, [_behaviour_fail("m1"), _bug_fail("c1")], run_id, "live")
    assert records.propose_lessons(tmp_path, 3, "r2") == []
    records.record_failures(tmp_path, [_behaviour_fail("m2"), _bug_fail("c1")], "r3", "live")
    drafted = records.propose_lessons(tmp_path, 3, "r3")
    assert [d["key"] for d in drafted] == ["reply_contains:recall"]
    assert drafted[0]["status"] == "proposed" and drafted[0]["effect"] == "guidance"
    assert records.propose_lessons(tmp_path, 3, "r4") == []  # not drafted twice


def test_importing_lessons_adds_them_as_proposed_only_once(tmp_path):
    for run_id in ("r1", "r2", "r3"):
        records.record_failures(tmp_path, [_behaviour_fail("m1")], run_id, "live")
    records.propose_lessons(tmp_path, 3, "r3")
    store = LessonStore(tmp_path / "lessons")
    now = datetime(2026, 11, 9, tzinfo=timezone.utc)
    ids = records.import_lessons(tmp_path, store, now)
    assert len(ids) == 1 and store.get(ids[0]).status == "proposed" and store.get(ids[0]).source == "outcomes"
    assert records.import_lessons(tmp_path, store, now) == []
    store.close()


def test_the_harness_has_no_path_to_approve_a_lesson_or_touch_the_gate():
    pkg = Path(__file__).parent.parent / "src" / "sutra_orchestrator" / "dogfood"
    source = "\n".join(p.read_text() for p in pkg.glob("*.py"))
    for forbidden in (".approve(", "AFFIRMATIVES", "NEGATIVES", "fast_path"):
        assert forbidden not in source


async def test_a_scenario_cut_short_by_the_budget_is_not_graded_or_promoted(tmp_path):
    steps = [{"kind": "user", "text": t, "speech_act": "chat", "addressee": "sutra"} for t in ("hmm", "maybe", "eh")]
    root = out_dir(tmp_path, [battery(scenario(steps=steps))])
    # Three hedges need three classifier calls; a budget of two runs out mid-scenario.
    report = await run(RunOptions(out_dir=root, seed=1, mode="live", batteries=("b",)), new_sandbox(), ScriptedModel(), budget=2)
    assert [r.status for r in report.results] == ["not_run"]
    assert report.promoted == [] and not (root / records.CORPUS).exists()
