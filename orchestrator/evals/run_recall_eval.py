"""Measure recall quality on a fixed set of memories and questions. No API key needed.

    python evals/run_recall_eval.py

Loads the memories into a throwaway store, asks each question, and checks that
the expected memory is among the recalled items. "Hard" questions paraphrase
with no words in common (for example "children" against "kids"); keyword search
is expected to miss those, and the hit rate on them is the number that decides
whether embeddings are worth adding. Negative questions must recall nothing.

Exits non-zero if the hit rate on ordinary questions drops below 90% or any
negative question recalls something.
"""

from __future__ import annotations

import asyncio
import json
import sys
import tempfile
from pathlib import Path

from sutra_orchestrator.memstore import SqliteMemory

DATA = Path(__file__).with_name("recall_cases.json")


async def main() -> int:
    cases = json.loads(DATA.read_text())
    with tempfile.TemporaryDirectory() as tmp:
        memory = SqliteMemory(Path(tmp) / "data")
        ids = [memory.add_memory(text).id for text in cases["memories"]]
        stored = len(memory.list_memories())
        assert stored == len(ids), f"{len(ids) - stored} memories were merged; make the set more distinct"

        easy_hits = easy_total = hard_hits = hard_total = 0
        misses: list[str] = []
        for case in cases["queries"]:
            items = await memory.recall(case["query"])
            want = cases["memories"][case["expect"]]
            hit = any(item.content == want for item in items)
            if case["hard"]:
                hard_total += 1
                hard_hits += hit
            else:
                easy_total += 1
                easy_hits += hit
                if not hit:
                    got = [i.content for i in items] or "nothing"
                    misses.append(f"  MISS {case['query']!r}: wanted {want!r}, got {got}")

        false_recalls = []
        for query in cases["negatives"]:
            items = await memory.recall(query)
            if items:
                false_recalls.append(f"  FALSE RECALL {query!r}: {[i.content for i in items]}")
        memory.close()

    print(f"memories: {stored}")
    print(f"ordinary questions: {easy_hits}/{easy_total} = {easy_hits / easy_total:.0%}")
    print(f"paraphrase questions (expected to be hard for keyword search): {hard_hits}/{hard_total}")
    print("\n".join(misses + false_recalls))
    print(f"negative questions that recalled something: {len(false_recalls)}")
    failed = easy_hits / easy_total < 0.9 or false_recalls
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
