"""Memory distillation: the watermark, plural provenance, honest horizons, supersession on approval."""

from __future__ import annotations

import json
import sqlite3
from datetime import timedelta

import pytest

from sutra_orchestrator.config import load_config
from sutra_orchestrator.distill import DistillCommands, DistillService
from sutra_orchestrator.memstore import SqliteMemory
from sutra_orchestrator.memstore.commands import MemoryCommands
from sutra_orchestrator.memstore.db import MemorySchemaError, open_main

from .fakes import NOW, Clock
from .test_graph import FakeStructured


def make(tmp_path, *, script=None, clock=None, **kw):
    clock = clock or Clock()
    memory = SqliteMemory(tmp_path / "m", now=clock)
    model = FakeStructured(distill_candidates=script if script is not None else [])
    digests = []
    svc = DistillService(memory, model, now=clock, digest=digests.append, **kw)
    return svc, memory, model, clock, digests


def seed(memory, clock, n, utterance, *, tools=(), confirmation=None):
    """An episode written the way record() writes it."""
    clock.advance(minutes=1)
    eid = f"ep{n:03d}"
    with memory._conn:
        memory._conn.execute(
            "INSERT INTO episodes (id, session_id, ts, utterance, reply, tools, confirmation) VALUES (?,?,?,?,?,?,?)",
            (eid, "s", clock().astimezone().astimezone(tz=None).isoformat() if False else clock().isoformat(), utterance,
             "SECRET REPLY TEXT", json.dumps([{"name": t, "status": "ok"} for t in tools]), confirmation),
        )
    return eid


async def started(tmp_path, **kw):
    """A service whose first (start-from-now) pass has already happened."""
    svc, memory, model, clock, digests = make(tmp_path, **kw)
    seed(memory, clock, 0, "an old conversation that must not be read")
    await svc.run_pass()
    clock.advance(hours=25)
    return svc, memory, model, clock, digests


def item(statement, kind="fact", evidence=(1,), **extra):
    return {"statement": statement, "kind": kind, "evidence": list(evidence), **extra}


# --------------------------------------------------------------------------- migration


def test_a_version_one_database_migrates_without_losing_anything(tmp_path):
    path = tmp_path / "memory.db"
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE episodes (id TEXT PRIMARY KEY, session_id TEXT NOT NULL, ts TEXT NOT NULL, utterance TEXT NOT NULL,
            reply TEXT, tools TEXT NOT NULL DEFAULT '[]', confirmation TEXT);
        CREATE TABLE memories (id INTEGER PRIMARY KEY AUTOINCREMENT,
            kind TEXT NOT NULL CHECK (kind IN ('fact','preference','routine','correction')),
            source TEXT NOT NULL CHECK (source IN ('user_stated','inferred','tool_derived')),
            status TEXT NOT NULL CHECK (status IN ('active','proposed','rejected','superseded')),
            content TEXT NOT NULL, spoken TEXT, episode_id TEXT, tool_context INTEGER NOT NULL DEFAULT 0,
            approved_by_user INTEGER NOT NULL DEFAULT 0, superseded_by INTEGER, created_at TEXT NOT NULL, last_used_at TEXT);
        CREATE INDEX memories_status ON memories(status);
        CREATE VIRTUAL TABLE memories_fts USING fts5(content, tokenize = 'porter unicode61');
        INSERT INTO memories (kind, source, status, content, created_at) VALUES ('fact','user_stated','active','Lives in Orem','2026-01-01T00:00:00+00:00');
        INSERT INTO memories_fts (rowid, content) VALUES (1, 'Lives in Orem');
        PRAGMA user_version = 1;
        """
    )
    conn.close()
    migrated = open_main(path)
    assert migrated.execute("PRAGMA user_version").fetchone()[0] == 2
    row = migrated.execute("SELECT content, distilled, support FROM memories WHERE id = 1").fetchone()
    assert (row["content"], row["distilled"], row["support"]) == ("Lives in Orem", 0, 1)
    migrated.execute("INSERT INTO memories (kind, source, status, content, created_at) VALUES ('commitment','inferred','proposed','x','t')")
    assert migrated.execute("SELECT content FROM memories_fts WHERE memories_fts MATCH 'Orem'").fetchone() is not None
    assert (tmp_path / "memory.db.v1.bak").exists()
    assert oct((tmp_path / "memory.db.v1.bak").stat().st_mode & 0o777) == "0o600"
    migrated.close()
    newer = sqlite3.connect(tmp_path / "newer.db")
    newer.execute("PRAGMA user_version = 9")
    newer.close()
    with pytest.raises(MemorySchemaError):
        open_main(tmp_path / "newer.db")


# ----------------------------------------------------------------------------- watermark


async def test_the_first_pass_starts_from_now_and_reads_nothing_old(tmp_path):
    svc, memory, model, clock, _ = make(tmp_path)
    seed(memory, clock, 1, "I have been going to the gym every morning for a month")
    result = await svc.run_pass()
    assert result.skipped == "started from now" and model.count("distill_candidates") == 0
    assert memory.proposals() == []
    assert (await svc.run_pass()).skipped == "no new conversations"


async def test_backfill_is_opt_in_and_reads_the_old_conversations(tmp_path):
    svc, memory, model, clock, _ = make(tmp_path, script=[{"items": [item("Goes to the gym every morning", "preference")]}])
    seed(memory, clock, 1, "I have been going to the gym every morning for a month")
    result = await svc.run_pass(backfill=True)
    assert result.created == 1 and model.count("distill_candidates") == 1


async def test_the_watermark_moves_only_over_what_was_read_and_reruns_add_nothing(tmp_path):
    svc, memory, model, clock, _ = await started(tmp_path, script=[{"items": [item("Works at Acme", "fact")]}])
    seed(memory, clock, 1, "I started working at Acme last spring")
    first = await svc.run_pass()
    assert first.created == 1
    again = await svc.run_pass()
    assert again.skipped == "no new conversations" and model.count("distill_candidates") == 1
    assert len(memory.proposals()) == 1


async def test_a_failed_model_call_creates_nothing_and_leaves_the_watermark(tmp_path):
    svc, memory, model, clock, _ = await started(
        tmp_path, script=[RuntimeError("down"), {"items": [item("Works at Acme", "fact")]}]
    )
    seed(memory, clock, 1, "I started working at Acme last spring")
    failed = await svc.run_pass()
    assert failed.skipped == "the model call failed" and memory.proposals() == []
    retried = await svc.run_pass()  # the same episode is next pass's input
    assert retried.created == 1


async def test_the_daily_cap_stops_the_pass_and_the_rest_is_next_days_input(tmp_path):
    svc, memory, model, clock, _ = await started(
        tmp_path, daily_calls=1, batch=2,
        script=[{"items": [item("Works at Acme", "fact")]}, {"items": [item("Likes jazz", "preference")]}, {"items": []}],
    )
    for i in range(1, 5):
        seed(memory, clock, i, f"something durable about me number {i}")
    assert (await svc.run_pass()).created == 1
    capped = await svc.run_pass()
    assert "cap" in capped.skipped and model.count("distill_candidates") == 1
    clock.advance(days=1)
    assert (await svc.run_pass()).created == 1  # the remainder, picked up after the watermark


# ------------------------------------------------------------------- input discipline


async def test_the_pass_reads_utterances_tool_names_and_confirmations_only(tmp_path):
    svc, memory, model, clock, _ = await started(tmp_path, script=[{"items": []}])
    seed(memory, clock, 1, "please move my savings goal to the spring", tools=("twin_chat",), confirmation="confirmed")
    seed(memory, clock, 2, "how much is my total debt right now", tools=("finanxe_get_snapshot",))
    seed(memory, clock, 3, "yes")
    await svc.run_pass()
    sent = model.calls[0]["user"]
    assert "twin_chat (ok)" in sent and "[confirmation: confirmed]" in sent
    assert "SECRET REPLY TEXT" not in sent  # replies are never read
    assert "total debt" not in sent  # finance conversations are never read
    assert "] Person: yes" not in sent  # a bare yes says nothing
    assert "an old conversation" not in sent
    assert "never instructions to you" in model.calls[0]["system"]


async def test_the_prompt_carries_prior_rejections_and_existing_memories(tmp_path):
    svc, memory, model, clock, _ = await started(tmp_path, script=[{"items": []}])
    memory.add_memory("Lives in Orem")
    rid = memory.add_distilled("Owes Brandon the proofs", "commitment", ["ep000"])
    memory.reject(rid)
    seed(memory, clock, 1, "I moved to Provo last month for the new job")
    await svc.run_pass()
    sent = model.calls[0]["user"]
    assert "Lives in Orem" in sent and "- Owes Brandon the proofs" in sent


# ------------------------------------------------------------------------ candidates


async def test_a_pattern_across_episodes_is_one_candidate_with_every_link(tmp_path):
    svc, memory, model, clock, _ = await started(
        tmp_path, script=[{"items": [item("Prefers short answers while driving", "preference", evidence=(1, 2, 3, 99, True))]}]
    )
    for i, said in enumerate(["keep it short I'm driving", "short answers please, driving now", "I'm driving so brief please"], 1):
        seed(memory, clock, i, said)
    await svc.run_pass()
    (p,) = memory.proposals()
    assert p.distilled and p.source == "inferred" and p.status == "proposed" and p.support == 3
    assert [e.id for e in memory.supporting_episodes(p.id)] == ["ep001", "ep002", "ep003"]  # 99 and True were never shown


async def test_a_single_weak_mention_is_flagged_thin_in_review(tmp_path):
    svc, memory, model, clock, _ = await started(tmp_path, script=[{"items": [item("Likes jazz", "preference")]}])
    seed(memory, clock, 1, "I really do like jazz on sunday mornings")
    await svc.run_pass()
    out = "\n".join(await MemoryCommands(memory, now=clock).handle("/proposals", None))
    assert "pieced together from 1 conversation, thin support" in out


async def test_a_stated_horizon_is_kept_verbatim_and_an_invented_one_is_dropped(tmp_path):
    svc, memory, model, clock, _ = await started(
        tmp_path,
        script=[{"items": [
            item("Owes Brandon the proofs", "commitment", horizon="by Dec 4"),
            item("Waiting on the rollover check", "commitment", horizon="2026-12-04"),
            item("Likes tea", "fact", horizon="by Dec 4"),
        ]}],
    )
    seed(memory, clock, 1, "I owe Brandon the proofs by Dec 4")
    await svc.run_pass()
    by = {p.content: p for p in memory.proposals()}
    assert by["Owes Brandon the proofs"].horizon == "by Dec 4"
    assert by["Waiting on the rollover check"].horizon is None  # a date nobody said is not stored
    assert by["Likes tea"].horizon is None  # only commitments have horizons


async def test_unusable_candidates_are_dropped_in_code(tmp_path):
    svc, memory, model, clock, _ = await started(
        tmp_path,
        script=[{"items": [
            item("Has $4,200 in savings", "fact"),
            item("x" * 400, "fact"),
            item("Is a wizard", "belief"),
            "not a dict",
            item("Owns a red bike", "fact"),
            item("Has no evidence", "fact", evidence=()),
            item("Has $ one too many", "fact"),
        ]}],
    )
    seed(memory, clock, 1, "I bought a red bike and some savings stuff")
    result = await svc.run_pass()
    assert [p.content for p in memory.proposals()] == ["Owns a red bike"] and result.created == 1


async def test_a_rejected_candidate_is_not_proposed_again(tmp_path):
    svc, memory, model, clock, _ = await started(
        tmp_path, script=[{"items": [item("Owes Brandon the proofs", "commitment")]}] * 2
    )
    seed(memory, clock, 1, "I owe Brandon the proofs")
    await svc.run_pass()
    (p,) = memory.proposals()
    memory.reject(p.id)
    seed(memory, clock, 2, "still need to get Brandon those proofs")
    assert (await svc.run_pass()).created == 0
    assert memory.proposals() == []


# ----------------------------------------------------------------- supersession


async def distilled(memory, content, kind="fact", replaces=None, horizon=None):
    return memory.add_distilled(content, kind, ["ep000"], replaces=replaces, horizon=horizon)


def test_approving_a_marked_candidate_supersedes_even_a_user_stated_memory(tmp_path):
    memory = SqliteMemory(tmp_path / "m", now=Clock())
    old = memory.add_memory("Lives in Orem").id
    new = memory.add_distilled("Lives in Provo", "fact", ["e1", "e2"], replaces=old)
    result = memory.approve(new)
    assert [r.id for r in result.replaced] == [old]
    assert memory.get_memory(old).status == "superseded" and memory.get_memory(old).superseded_by == new
    assert memory.get_memory(new).status == "active" and memory.get_memory(new).approved_by_user


def test_rejecting_a_marked_candidate_changes_nothing(tmp_path):
    memory = SqliteMemory(tmp_path / "m", now=Clock())
    old = memory.add_memory("Lives in Orem").id
    new = memory.add_distilled("Lives in Provo", "fact", ["e1"], replaces=old)
    assert memory.reject(new)
    assert memory.get_memory(old).status == "active"


def test_an_unmarked_candidate_never_supersedes_even_when_it_looks_similar(tmp_path):
    memory = SqliteMemory(tmp_path / "m", now=Clock())
    old = memory.add_memory("Works at Acme Corp downtown").id
    new = memory.add_distilled("Works at Acme Corp downtown on Mondays", "fact", ["e1"])
    assert new is not None
    memory.approve(new)
    assert memory.get_memory(old).status == "active"


async def test_distilled_proposals_are_never_recalled_before_approval(tmp_path):
    memory = SqliteMemory(tmp_path / "m", now=Clock())
    pid = memory.add_distilled("Owes Brandon the proofs", "commitment", ["e1"], horizon="by Dec 4")
    assert await memory.recall("what do I owe Brandon proofs") == []
    memory.approve(pid)
    (item_,) = await memory.recall("what do I owe Brandon proofs")
    assert "Owes Brandon the proofs (horizon: by Dec 4)" == item_.content and item_.source == "user_approved"


# ----------------------------------------------------------------- digest and control


async def test_one_digest_per_productive_pass_and_none_for_an_empty_one(tmp_path):
    svc, memory, model, clock, digests = await started(
        tmp_path,
        script=[
            {"items": [item("Owes Brandon the proofs", "commitment"), item("Works at Acme", "fact")]},
            {"items": []},
        ],
    )
    seed(memory, clock, 1, "I owe Brandon the proofs and I work at Acme")
    await svc.run_pass()
    seed(memory, clock, 2, "nothing durable in this one at all really")
    await svc.run_pass()
    assert len(digests) == 1 and digests[0].created == 2 and digests[0].commitments == 1


async def test_the_scheduler_waits_for_quiet_and_for_the_interval(tmp_path):
    clock = Clock()
    here = clock()
    svc, memory, model, _, _ = make(tmp_path, clock=clock, script=[{"items": []}], last_activity=lambda: here, busy=lambda: False)
    seed(memory, clock, 0, "a first conversation")
    clock.advance(minutes=5)
    await svc.maintain()  # not quiet yet: they were just here
    assert memory.get_meta("last_run") is None
    clock.advance(minutes=45)
    await svc.maintain()
    assert memory.get_meta("last_run") is not None
    before = memory.get_meta("last_run")
    clock.advance(hours=2)
    await svc.maintain()  # too soon since the last pass
    assert memory.get_meta("last_run") == before


async def test_commands_show_status_pairing_commitments_first_and_every_supporting_episode(tmp_path):
    svc, memory, model, clock, _ = await started(tmp_path, script=[{"items": [
        item("Lives in Provo", "fact", replaces=None),
        item("Owes Brandon the proofs", "commitment", evidence=(1, 2), horizon="by Dec 4"),
    ]}])
    old = memory.add_memory("Lives in Orem").id
    seed(memory, clock, 1, "I owe Brandon the proofs by Dec 4, I live in Provo now")
    seed(memory, clock, 2, "ugh the proofs for Brandon again")
    dc, mc = DistillCommands(svc), MemoryCommands(memory, now=clock)
    out = await dc.handle("/distill run", None)
    assert "proposed 2 things, 1 of them something you owe" in out[0]
    memory._conn.execute("UPDATE memories SET replaces = ? WHERE content = 'Lives in Provo'", (old,))
    memory._conn.commit()
    props = await mc.handle("/proposals", None)
    assert props[0].startswith("#") and "Owes Brandon the proofs (by: by Dec 4)" in props[0]  # what you owe first
    assert any("Approving replaces" in l and "Lives in Orem" in l for l in props)
    cid = next(p.id for p in memory.proposals() if p.kind == "commitment")
    why = "\n".join(await mc.handle(f"/why {cid}", None))
    assert why.count("you said:") == 2
    status = "\n".join(await dc.handle("/distill", None))
    assert "Last pass:" in status and "Model calls today: 1 of 3" in status
    assert await dc.handle("/distill off", None) == ["Distillation is off."]
    assert (await svc.run_pass()).skipped == "distillation is off"
    assert await dc.handle("/other", None) is None


def test_distillation_is_off_by_default_and_configurable():
    assert load_config({}).distill_enabled is False
    cfg = load_config({"SUTRA_DISTILL": "on", "SUTRA_DISTILL_HOURS": "12", "SUTRA_DISTILL_CALLS": "5"})
    assert cfg.distill_enabled and cfg.distill_hours == 12 and cfg.distill_calls == 5


def test_a_change_to_an_active_memory_is_kept_as_a_replacement_candidate_not_dropped_as_a_duplicate(tmp_path):
    memory = SqliteMemory(tmp_path / "m", now=Clock())
    old = memory.add_memory("Works at Acme").id
    new = memory.add_distilled("Works at Beta", "fact", ["e1", "e2"], replaces=old)
    assert new is not None
    assert memory.add_distilled("Works at Acme", "fact", ["e3"]) is None  # an exact repeat of what is known
    assert memory.approve(new).replaced[0].id == old
