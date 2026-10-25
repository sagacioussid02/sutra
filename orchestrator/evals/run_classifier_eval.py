"""Run the real confirmation classifier against the labelled example set.

    ANTHROPIC_API_KEY=... python evals/run_classifier_eval.py

Reports accuracy per label and every misclassification. A false ``affirm``
(the classifier said yes when the right label was anything else) is the
dangerous error: it exits non-zero if there is even one.

Uses the same fast path and classifier model setting (SUTRA_CLASSIFIER_MODEL)
as the orchestrator, so the numbers reflect what a real confirmation turn does.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from collections import Counter
from pathlib import Path

from sutra_orchestrator.classifier import AFFIRM, IntentClassifier, fast_path
from sutra_orchestrator.config import DEFAULT_CLASSIFIER_MODEL, DEFAULT_MODEL
from sutra_orchestrator.model import AnthropicModel

DATA = Path(__file__).with_name("confirmation_replies.jsonl")
DESCRIPTIONS = [
    "Create a goal named Vacation with a target of 2000 dollars.",
    "Redirect payments for your Visa card so they come from your checking account.",
    "Add a calendar event called Rent due on the first of the month.",
]


async def main() -> int:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("ANTHROPIC_API_KEY is required", file=sys.stderr)
        return 2
    classifier_model = os.environ.get("SUTRA_CLASSIFIER_MODEL", DEFAULT_CLASSIFIER_MODEL)
    model = AnthropicModel(api_key, DEFAULT_MODEL, classifier_model)
    classifier = IntentClassifier(model, timeout=20)

    rows = [json.loads(line) for line in DATA.read_text().splitlines() if line.strip()]
    right: Counter[str] = Counter()
    total: Counter[str] = Counter()
    wrong: list[tuple[str, str, str, str]] = []
    false_affirms = 0

    for i, row in enumerate(rows):
        description = DESCRIPTIONS[i % len(DESCRIPTIONS)]
        predicted = await classifier.classify(description, row["reply"])
        total[row["label"]] += 1
        if predicted == row["label"]:
            right[row["label"]] += 1
        else:
            how = "fast path" if fast_path(row["reply"]) else "model"
            wrong.append((row["reply"], row["label"], predicted, how))
            if predicted == AFFIRM:
                false_affirms += 1

    print(f"classifier model: {classifier_model}")
    for label in ("affirm", "deny", "modify", "unclear"):
        print(f"  {label:8s} {right[label]:2d}/{total[label]:2d}")
    print(f"  overall  {sum(right.values())}/{len(rows)}")
    for reply, expected, predicted, how in wrong:
        print(f"  MISS ({how}): {reply!r}: expected {expected}, got {predicted}")
    print(f"false affirms: {false_affirms}")
    return 1 if false_affirms else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
