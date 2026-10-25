"""The labelled confirmation-reply set stays well-formed and agrees with the fast path."""

from __future__ import annotations

import json
from pathlib import Path

from sutra_orchestrator.classifier import LABELS, fast_path

DATA = Path(__file__).parent.parent / "evals" / "confirmation_replies.jsonl"


def rows():
    return [json.loads(line) for line in DATA.read_text().splitlines() if line.strip()]


def test_set_has_at_least_forty_rows_covering_every_label():
    data = rows()
    assert len(data) >= 40
    labels = {r["label"] for r in data}
    assert labels == set(LABELS)
    assert all(r["label"] in LABELS and r["reply"].strip() for r in data)


def test_no_duplicate_replies():
    replies = [r["reply"].lower() for r in rows()]
    assert len(replies) == len(set(replies))


def test_fast_path_never_disagrees_with_the_labels():
    for row in rows():
        resolved = fast_path(row["reply"])
        if resolved is not None:
            assert resolved == row["label"], row
