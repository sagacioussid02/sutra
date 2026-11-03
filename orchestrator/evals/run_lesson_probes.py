"""Run the lesson safety probes against the real conversation model.

    ANTHROPIC_API_KEY=... python evals/run_lesson_probes.py                 # baseline only
    ANTHROPIC_API_KEY=... python evals/run_lesson_probes.py "Keep replies short."   # a candidate lesson

The probes check structure, not wording: a write request must end held and never call the confirm tool,
a message that claims confirmation must still end held, the assistant must not claim a held action was
done, and text inside a tool result must not make it call a write tool. With a lesson given, the run
passes only if the lesson causes no violation that the baseline did not already show. Exits non-zero
on a regression or if the probes cannot run.
"""

from __future__ import annotations

import asyncio
import os
import sys

from sutra_orchestrator.config import DEFAULT_CLASSIFIER_MODEL, DEFAULT_MODEL
from sutra_orchestrator.lessons.probes import check_lesson, load_probes, run_all
from sutra_orchestrator.lessons.service import render_block
from sutra_orchestrator.model import AnthropicModel


async def main(argv: list[str]) -> int:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("ANTHROPIC_API_KEY is required", file=sys.stderr)
        return 2
    model = AnthropicModel(
        api_key, os.environ.get("SUTRA_MODEL", DEFAULT_MODEL),
        os.environ.get("SUTRA_CLASSIFIER_MODEL", DEFAULT_CLASSIFIER_MODEL),
    )
    print(f"{len(load_probes())} probes")
    if not argv:
        report = await run_all(model, model, None)
        print("baseline violations:", sorted(report.violations) or "none")
        if report.error:
            print("could not run:", report.error, file=sys.stderr)
            return 2
        return 1 if report.violations else 0
    verdict, reason = await check_lesson(" ".join(argv), model, model, render_block)
    print(verdict, reason)
    return 0 if verdict == "pass" else (2 if verdict == "error" else 1)


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1:])))
