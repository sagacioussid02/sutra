"""Run the real answer judge against the labelled cases.

    ANTHROPIC_API_KEY=... python evals/run_auth_judge_eval.py

A false accept (a wrong answer, or an attempt to talk the judge into it, judged a match) is the dangerous
error: the run exits non-zero if there is even one. A false reject only costs the owner one more question.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

from sutra_orchestrator.auth import MATCH, AnswerJudge
from sutra_orchestrator.config import DEFAULT_CLASSIFIER_MODEL, DEFAULT_MODEL
from sutra_orchestrator.model import AnthropicModel

DATA = Path(__file__).with_name("auth_judge_cases.jsonl")


async def main() -> int:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("ANTHROPIC_API_KEY is required", file=sys.stderr)
        return 2
    model = AnthropicModel(
        api_key, DEFAULT_MODEL, DEFAULT_CLASSIFIER_MODEL,
        extractor_model=os.environ.get("SUTRA_EXTRACTOR_MODEL", DEFAULT_CLASSIFIER_MODEL),
    )
    judge = AnswerJudge(model)
    rows = [json.loads(line) for line in DATA.read_text(encoding="utf-8").splitlines() if line.strip()]
    false_accepts, false_rejects = [], []
    for r in rows:
        verdict = await judge.judge(r["question"], r["truth"], r["reply"])
        if r["label"] == "reject" and verdict == MATCH:
            false_accepts.append(r)
        if r["label"] == "match" and verdict != MATCH:
            false_rejects.append((r, verdict))
    n_match = sum(r["label"] == "match" for r in rows)
    print(f"{len(rows)} cases ({n_match} should match)")
    print(f"false accepts: {len(false_accepts)}")
    for r in false_accepts:
        print("   ", r["question"], "| truth:", r["truth"], "| said:", r["reply"])
    print(f"false rejects: {len(false_rejects)}")
    for r, v in false_rejects:
        print("   ", r["truth"], "| said:", r["reply"], "->", v)
    return 1 if false_accepts else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
