"""``python -m sutra_orchestrator.dogfood``: run batteries, read the scorecard, import lesson drafts.

    run             run the batteries in the sandbox and record the results
    scorecard       print the readiness trend per capability
    import-lessons  add drafted lesson proposals to your lesson store, as "proposed"

``run`` defaults to the scripted model: free, deterministic, and enough for
the reminder, confirmation-gate and offer-cap batteries. ``--live`` uses the
real model (needs ANTHROPIC_API_KEY) and runs every battery, inside the
SUTRA_DOGFOOD_CALL_BUDGET. Either way nothing is spoken, sent, booked or
paid, and no real store is read or written.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

from ..errors import OrchestratorError
from .config import ORCHESTRATOR_DIR, load_dogfood_config
from .harness import RunOptions, run
from .profile import ProfileError, new_sandbox
from .records import import_lessons, render_scorecard
from .stubs import ScriptedModel


def _real_dirs() -> tuple[Path, ...]:
    """Where the live assistant keeps its stores, so the sandbox can prove it is elsewhere."""
    dirs = {ORCHESTRATOR_DIR / "data", Path("~/.sutra").expanduser()}
    for name, value in os.environ.items():
        if name.startswith("SUTRA_") and name.endswith("_DIR") and not name.startswith("SUTRA_DOGFOOD") and value:
            path = Path(value).expanduser()
            dirs.add(path if path.is_absolute() else ORCHESTRATOR_DIR / path)
    return tuple(sorted(dirs))


def _live_model(grader: str):
    from ..config import load_config
    from ..model import AnthropicModel

    env = dict(os.environ)
    # The harness never talks to the gateway, so it does not need the gateway token.
    env.setdefault("SUTRA_TOKEN", "dogfood-sandbox-no-gateway")
    config = load_config(env)
    model = AnthropicModel(
        config.api_key, config.model, config.classifier_model,
        extractor_model=config.extractor_model, agent_model=config.agent_model,
    )
    return model, grader or config.model


async def _run(args: argparse.Namespace) -> int:
    cfg = load_dogfood_config()
    mode = "live" if args.live else "scripted"
    grader = cfg.grader_model
    if mode == "live":
        try:
            model, grader = _live_model(grader)
        except OrchestratorError as exc:
            print(f"cannot run --live: {exc}", file=sys.stderr)
            return 2
    else:
        model = ScriptedModel()
    profile = new_sandbox(_real_dirs())
    options = RunOptions(
        out_dir=cfg.out_dir, mode=mode, batteries=tuple(args.battery or ()), seed=args.seed,
        per_template=args.per_template, include_corpus=not args.no_corpus, rubric=args.rubric,
        grader_model=grader, lesson_runs=cfg.lesson_runs, personal_markers=cfg.personal_markers,
        write=not args.no_write,
    )
    try:
        report = await run(options, profile, model, budget=cfg.call_budget)
    except ProfileError as exc:
        print(f"aborted: {exc}", file=sys.stderr)
        return 2
    finally:
        shutil.rmtree(profile.root, ignore_errors=True)
    print(report.text())
    return 0 if report.ok else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m sutra_orchestrator.dogfood")
    sub = parser.add_subparsers(dest="command", required=True)
    r = sub.add_parser("run", help="run batteries in the sandbox")
    r.add_argument("--battery", action="append", help="run only this battery (repeatable; 'generated' for templates)")
    r.add_argument("--live", action="store_true", help="use the real model (costs calls, within the budget)")
    r.add_argument("--rubric", action="store_true", help="also grade soft criteria with the grader model (live only)")
    r.add_argument("--seed", type=int, help="fixed seed for generated scenarios, to reproduce a run")
    r.add_argument("--per-template", type=int, default=3, help="generated scenarios per template")
    r.add_argument("--no-corpus", action="store_true", help="skip the promoted eval corpus")
    r.add_argument("--no-write", action="store_true", help="report only: write no dataset, corpus or scorecard")
    s = sub.add_parser("scorecard", help="print the readiness trend")
    s.add_argument("--last", type=int, default=8)
    i = sub.add_parser("import-lessons", help="add drafted lessons to a lesson store as proposed")
    i.add_argument("lessons_dir", help="the lessons directory (SUTRA_LESSONS_DIR of the assistant)")
    args = parser.parse_args(argv)

    if args.command == "run":
        return asyncio.run(_run(args))
    cfg = load_dogfood_config()
    if args.command == "scorecard":
        print(render_scorecard(cfg.out_dir, args.last))
        return 0
    from ..lessons.store import LessonStore

    store = LessonStore(Path(args.lessons_dir).expanduser())
    try:
        added = import_lessons(cfg.out_dir, store, datetime.now(timezone.utc))
    finally:
        store.close()
    print(f"{len(added)} lesson proposal(s) added as proposed; approve or reject them as usual.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
