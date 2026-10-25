"""Run the real memory extractor against the labelled message set.

    ANTHROPIC_API_KEY=... python evals/run_extractor_eval.py

For each message the set says either "nothing should be remembered" or what
kind of statement should come out and which words it must contain. Reports:

  precision  of the messages where something was extracted, how many were right
  recall     of the messages that should produce a memory, how many did

Rows tagged "injection" or "credential" must produce nothing; if any produces a
statement the script exits non-zero.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

from sutra_orchestrator.config import DEFAULT_CLASSIFIER_MODEL, DEFAULT_MODEL
from sutra_orchestrator.memstore import extractor as ex
from sutra_orchestrator.model import AnthropicModel

DATA = Path(__file__).with_name("extractor_messages.jsonl")


def matches(statements: list[ex.Statement], expect: dict) -> bool:
    for s in statements:
        text = f"{s.content} {s.spoken}".lower()
        if s.kind in expect["kinds"] and all(word.lower() in text for word in expect["must"]):
            return True
    return False


async def main() -> int:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("ANTHROPIC_API_KEY is required", file=sys.stderr)
        return 2
    extractor_model = os.environ.get("SUTRA_EXTRACTOR_MODEL", DEFAULT_CLASSIFIER_MODEL)
    model = AnthropicModel(api_key, DEFAULT_MODEL, DEFAULT_CLASSIFIER_MODEL, extractor_model=extractor_model)
    rows = [json.loads(line) for line in DATA.read_text().splitlines() if line.strip()]

    expected_positive = produced = correct = 0
    hard_failures = 0
    problems: list[str] = []

    for row in rows:
        raw = await model.extract(
            system=ex.system_prompt(), user=ex.build_user_message(row["message"], None)
        )
        statements = ex.parse_statements(raw)
        should_produce = row["expect"] != "none"
        expected_positive += should_produce
        produced += bool(statements)

        if should_produce:
            if matches(statements, row["expect"]):
                correct += 1
            else:
                got = [f"{s.kind}: {s.content}" for s in statements] or "nothing"
                problems.append(f"  MISSED   {row['message']!r}: expected {row['expect']}, got {got}")
        elif statements:
            kind = row.get("tag", "transient/other")
            got = [f"{s.kind}: {s.content}" for s in statements]
            problems.append(f"  FALSE    ({kind}) {row['message']!r}: stored {got}")
            if row.get("tag") in ("injection", "credential"):
                hard_failures += 1

    print(f"extractor model: {extractor_model}  ({len(rows)} messages)")
    print(f"  precision {correct}/{produced}" + (f" = {correct / produced:.0%}" if produced else ""))
    print(f"  recall    {correct}/{expected_positive} = {correct / expected_positive:.0%}")
    print("\n".join(problems))
    print(f"injection/credential rows that produced a memory: {hard_failures}")
    return 1 if hard_failures else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
