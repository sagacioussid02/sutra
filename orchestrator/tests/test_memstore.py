"""assistant-memory: storage, recall, extraction, proposals, notices, archive."""

from __future__ import annotations

import hashlib
import socket
import sqlite3
import stat
from datetime import date, timedelta

import pytest

from sutra_orchestrator.memory import SOURCE_USER_APPROVED, SOURCE_USER_STATED, ToolCallRecord, ToolContext
from sutra_orchestrator.memstore import MemorySchemaError, SqliteMemory
from sutra_orchestrator.memstore.db import open_main

from .fakes import NOW, Clock
from .memhelpers import FakeExtractor, make_memory, run_turn, stmt


def rows(memory: SqliteMemory):
    return memory.list_memories()


# --- persistence, privacy, versioning ---------------------------------------------------------------


async def test_a_stated_preference_survives_a_restart_and_is_recalled(tmp_path):
    extractor = FakeExtractor({"short": [stmt("Keep your answers short.", "You want short answers.", "preference")]})
    first = make_memory(tmp_path, extractor)
    await run_turn(first, "please keep your answers short")
    first.close()

    second = make_memory(tmp_path, FakeExtractor())  # a new session
    items = await second.recall("give me a short summary of my answers")

    assert [i.content for i in items] == ["Keep your answers short."]
    assert items[0].source == SOURCE_USER_STATED


async def test_database_files_are_owner_only(tmp_path):
    clock = Clock()
    memory = make_memory(tmp_path, FakeExtractor(), clock, hot_days=1)
    await run_turn(memory, "hello there", clock=clock)
    clock.advance(days=3)
    memory.close()
    memory = make_memory(tmp_path, FakeExtractor(), clock, hot_days=1)  # archives the old episode

    for name in ("memory.db", "memory-archive.db"):
        mode = stat.S_IMODE((tmp_path / "data" / name).stat().st_mode)
        assert mode == 0o600, f"{name} is {oct(mode)}"


async def test_the_provider_opens_no_network_connections(tmp_path, monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("memory attempted a network operation")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "getaddrinfo", refuse)
    extractor = FakeExtractor({"15th": [stmt("I get paid on the 15th.")]})
    memory = make_memory(tmp_path, extractor)
    await run_turn(memory, "I get paid on the 15th")
    await memory.recall("when do I get paid")
    memory.search_memories("paid")


async def test_a_newer_schema_is_refused_without_modifying_the_file(tmp_path):
    path = tmp_path / "data" / "memory.db"
    open_main(path).close()
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA user_version = 99")
    conn.commit()
    conn.close()
    before = hashlib.sha256(path.read_bytes()).hexdigest()

    with pytest.raises(MemorySchemaError, match="schema version 99"):
        make_memory(tmp_path)

    assert hashlib.sha256(path.read_bytes()).hexdigest() == before


# --- provenance ----------------------------------------------------------------------------------------


async def test_memories_record_source_kind_status_and_the_episode_they_came_from(tmp_path):
    extractor = FakeExtractor({"15th": [stmt("I get paid on the 15th.", kind="fact")]})
    memory = make_memory(tmp_path, extractor)
    await run_turn(memory, "I get paid on the 15th", reply="Noted, thanks.")

    (m,) = rows(memory)
    assert (m.kind, m.source, m.status) == ("fact", "user_stated", "active")
    assert m.created_at is not None and m.episode_id

    found = memory.why(m.id)
    assert found is not None
    _, episode = found
    assert episode.utterance == "I get paid on the 15th" and episode.reply == "Noted, thanks."


async def test_why_for_a_memory_added_directly_has_no_episode(tmp_path):
    memory = make_memory(tmp_path)
    result = memory.add_memory("I prefer metric units")
    _, episode = memory.why(result.id)
    assert episode is None


# --- the extractor ----------------------------------------------------------------------------------------


async def test_durable_fact_preference_and_correction_become_memories(tmp_path):
    extractor = FakeExtractor(
        {
            "paid": [stmt("I get paid on the 15th.", kind="fact")],
            "short": [stmt("Keep answers short.", kind="preference")],
            "savings": [stmt("My main account is my savings account.", kind="correction")],
        }
    )
    memory = make_memory(tmp_path, extractor)
    await run_turn(memory, "I get paid on the 15th")
    await run_turn(memory, "keep answers short please")
    await run_turn(memory, "that's not checking, it's my savings account")

    kinds = {m.kind for m in rows(memory)}
    assert kinds == {"fact", "preference", "correction"}
    assert all(m.source == "user_stated" for m in rows(memory))


async def test_a_transient_statement_creates_no_memory(tmp_path):
    memory = make_memory(tmp_path, FakeExtractor())  # extractor returns nothing for "tired"
    await run_turn(memory, "I'm tired today")
    assert rows(memory) == []


async def test_extractor_input_has_only_the_users_messages(tmp_path):
    extractor = FakeExtractor()
    memory = make_memory(tmp_path, extractor)
    await run_turn(
        memory,
        "first user message",
        reply="SECRET-REPLY-ONE with SECRET-TOOL-RESULT",
        tools=(ToolCallRecord("finanxe_list_debts", "ok"),),
    )
    await run_turn(memory, "second user message", reply="SECRET-REPLY-TWO")

    assert len(extractor.calls) == 2
    second = extractor.calls[1]["user"]
    assert "second user message" in second and "first user message" in second  # prior turn
    for text in (extractor.calls[0]["user"], second):
        assert "SECRET" not in text and "finanxe_list_debts" not in text


async def test_extractor_error_timeout_and_invalid_output_create_nothing(tmp_path):
    extractor = FakeExtractor()
    memory = make_memory(tmp_path, extractor)

    extractor.error = RuntimeError("api down")
    await run_turn(memory, "I get paid on the 15th")

    extractor.error = None
    for bad in (
        "not a list",
        [{"content": "x", "spoken": "x", "kind": "fact"}],  # too short
        [{"content": "I like tea.", "spoken": "You like tea.", "kind": "mood"}],  # bad kind
        [{"spoken": "You like tea.", "kind": "fact"}],  # no content
        ["a string"],
        None,
    ):
        extractor.raw = bad
        await run_turn(memory, "I like tea very much")

    assert rows(memory) == []
    # And the episodes were still recorded: the turn itself was unaffected.
    assert memory._conn.execute("SELECT COUNT(*) FROM episodes").fetchone()[0] == 7


async def test_at_most_three_statements_per_message_are_kept(tmp_path):
    extractor = FakeExtractor({"lots": [stmt(f"Statement number {i} here.") for i in range(6)]})
    memory = make_memory(tmp_path, extractor)
    await run_turn(memory, "lots of facts")
    assert len(rows(memory)) == 3


async def test_trivial_replies_do_not_call_the_extractor(tmp_path):
    extractor = FakeExtractor()
    memory = make_memory(tmp_path, extractor)
    for text in ("yes", "No.", "go ahead", "  "):
        await run_turn(memory, text)
    assert extractor.calls == []


async def test_extraction_does_not_delay_record(tmp_path):
    """record() returns before the extractor finishes; flush() waits for it."""
    import asyncio

    gate = asyncio.Event()

    class Slow(FakeExtractor):
        async def extract(self, *, system, user):
            await gate.wait()
            return [stmt("I get paid on the 15th.")]

    memory = make_memory(tmp_path, Slow())
    from sutra_orchestrator.memory import Episode

    await memory.recall("I get paid on the 15th")
    await memory.record(Episode(utterance="I get paid on the 15th", reply="ok"))
    assert rows(memory) == []  # extractor still running; record() has already returned
    gate.set()
    await memory.flush()
    assert len(rows(memory)) == 1


# --- supersession and duplicates -------------------------------------------------------------------------


async def test_a_changed_fact_supersedes_the_old_one(tmp_path):
    extractor = FakeExtractor(
        {
            "15th": [stmt("I get paid on the 15th.", "You get paid on the 15th.")],
            "1st": [stmt("I get paid on the 1st.", "You get paid on the 1st.")],
        }
    )
    memory = make_memory(tmp_path, extractor)
    await run_turn(memory, "I get paid on the 15th")
    await run_turn(memory, "actually I get paid on the 1st now")

    by_content = {m.content: m for m in rows(memory)}
    assert by_content["I get paid on the 15th."].status == "superseded"
    assert by_content["I get paid on the 15th."].superseded_by == by_content["I get paid on the 1st."].id
    assert by_content["I get paid on the 1st."].status == "active"

    # Superseded is not recalled, but is still listed and searchable.
    items = await memory.recall("when do I get paid")
    assert [i.content for i in items] == ["I get paid on the 1st."]
    assert any(m.status == "superseded" for m in memory.search_memories("paid"))


async def test_unrelated_facts_of_the_same_kind_do_not_supersede_each_other(tmp_path):
    memory = make_memory(tmp_path)
    memory.add_memory("I like dark mode")
    memory.add_memory("I like short answers")
    assert {m.status for m in rows(memory)} == {"active"}


async def test_an_exact_duplicate_is_not_added_again(tmp_path):
    memory = make_memory(tmp_path)
    first = memory.add_memory("I get paid on the 15th.")
    again = memory.add_memory("i get paid on the 15th")
    assert first.id is not None and again.id is None
    assert len(rows(memory)) == 1


# --- recall --------------------------------------------------------------------------------------------------


async def test_a_relevant_memory_is_recalled_and_an_unrelated_query_recalls_nothing(tmp_path):
    memory = make_memory(tmp_path)
    memory.add_memory("Rent is due on the 1st of the month.")
    assert [i.content for i in await memory.recall("when is rent due?")] == [
        "Rent is due on the 1st of the month."
    ]
    assert await memory.recall("what is the weather like in Paris") == []
    assert await memory.recall("the and of") == []  # only stopwords


GROCERY_FACTS = [
    "Groceries come from Trader Joes on Sundays",
    "Peanut allergy means check every grocery label",
    "Instacart delivers groceries on Fridays",
    "Weekly groceries budget is four hundred dollars",
    "Costco trips happen monthly for bulk groceries",
    "Farmers market groceries are paid in cash",
    "Vegetarian household so groceries skip meat",
    "Groceries paid with the blue Visa card",
]


async def test_recall_respects_the_count_and_character_limits(tmp_path):
    memory = make_memory(tmp_path, recall_limit=3)
    for fact in GROCERY_FACTS:
        memory.add_memory(fact)
    assert len(rows(memory)) == len(GROCERY_FACTS)  # distinct facts, none merged
    assert len(await memory.recall("groceries")) == 3

    small = make_memory(tmp_path / "other", recall_limit=8, char_budget=100)
    for fact in GROCERY_FACTS:
        small.add_memory(fact)
    items = await small.recall("groceries")
    assert 1 <= len(items) < 8
    assert sum(len(i.content) for i in items[:-1]) <= 100


async def test_recall_updates_last_used(tmp_path):
    clock = Clock()
    memory = make_memory(tmp_path, clock=clock)
    memory_id = memory.add_memory("Rent is due on the 1st.").id
    assert memory.get_memory(memory_id).last_used_at is None
    clock.advance(days=2)
    await memory.recall("when is rent due")
    assert memory.get_memory(memory_id).last_used_at == clock()


async def test_on_equal_relevance_a_newer_memory_outranks_an_older_one(tmp_path):
    clock = Clock()
    memory = make_memory(tmp_path, clock=clock, recall_limit=1)
    memory.add_memory("Alpha groceries delivered Sundays")  # same length and shape, so equal bm25
    clock.advance(days=120)
    memory.add_memory("Bravo groceries delivered Fridays")

    items = await memory.recall("groceries")

    assert [i.content for i in items] == ["Bravo groceries delivered Fridays"]


async def test_on_equal_relevance_a_recently_used_memory_outranks_an_unused_one(tmp_path):
    clock = Clock()
    memory = make_memory(tmp_path, clock=clock, recall_limit=1)
    used = memory.add_memory("Alpha groceries delivered Sundays").id
    memory.add_memory("Bravo groceries delivered Fridays")
    # Use the first one by asking about it specifically, then ask a tie-breaking question.
    clock.advance(days=1)
    memory._conn.execute("UPDATE memories SET last_used_at = ? WHERE id = ?", (clock().isoformat(), used))
    memory._conn.commit()
    # Make the two equally old so only last-used differs.
    memory._conn.execute("UPDATE memories SET created_at = ?", (clock().isoformat(),))
    memory._conn.commit()

    items = await memory.recall("groceries")

    assert [i.content for i in items] == ["Alpha groceries delivered Sundays"]


async def test_odd_characters_in_a_query_cannot_break_recall(tmp_path):
    memory = make_memory(tmp_path)
    memory.add_memory("Rent is due on the 1st.")
    for query in ['rent" OR "x', "rent AND", "rent*", "(rent", "NEAR(rent due)", "rent -due", "'; DROP TABLE memories;--"]:
        await memory.recall(query)  # must not raise
        memory.search_memories(query)
    assert len(rows(memory)) == 1


async def test_a_short_followup_borrows_the_previous_message_for_recall(tmp_path):
    memory = make_memory(tmp_path, FakeExtractor())
    memory.add_memory("Rent is due on the 1st.")
    await run_turn(memory, "tell me about rent")
    items = await memory.recall("and that one?")
    assert [i.content for i in items] == ["Rent is due on the 1st."]


# --- user controls --------------------------------------------------------------------------------------------


async def test_forget_removes_the_row_and_its_search_index_entry(tmp_path):
    memory = make_memory(tmp_path)
    keep = memory.add_memory("I prefer metric units").id
    gone = memory.add_memory("Rent is due on the 1st").id

    assert memory.delete_memory(gone) is True
    assert memory.get_memory(gone) is None
    fts = memory._conn.execute("SELECT COUNT(*) FROM memories_fts WHERE rowid = ?", (gone,)).fetchone()[0]
    assert fts == 0
    assert await memory.recall("when is rent due") == []
    assert memory.get_memory(keep) is not None
    assert memory.delete_memory(gone) is False  # already gone


async def test_deleting_a_superseding_memory_clears_the_dangling_pointer(tmp_path):
    memory = make_memory(tmp_path)
    old = memory.add_memory("I get paid on the 15th").id
    new = memory.add_memory("I get paid on the 1st").id
    assert memory.get_memory(old).superseded_by == new
    memory.delete_memory(new)
    assert memory.get_memory(old).superseded_by is None


async def test_ids_are_never_reused(tmp_path):
    memory = make_memory(tmp_path)
    first = memory.add_memory("one fact about me").id
    memory.delete_memory(first)
    assert memory.add_memory("another fact about me").id != first


# --- episodes -------------------------------------------------------------------------------------------------


async def test_episodes_store_tool_names_and_status_but_no_payloads(tmp_path):
    memory = make_memory(tmp_path, FakeExtractor())
    await run_turn(
        memory,
        "my debts?",
        reply="Three debts.",
        tools=(ToolCallRecord("finanxe_list_debts", "ok"),),
        confirmation="confirmed",
    )
    row = memory._conn.execute("SELECT * FROM episodes").fetchone()
    assert row["utterance"] == "my debts?" and row["reply"] == "Three debts."
    assert row["confirmation"] == "confirmed"
    assert '"finanxe_list_debts"' in row["tools"] and '"ok"' in row["tools"]


async def test_reply_recording_can_be_turned_off(tmp_path):
    memory = make_memory(tmp_path, FakeExtractor(), record_replies=False)
    await run_turn(memory, "my debts?", reply="You owe 12,431 dollars.")
    row = memory._conn.execute("SELECT * FROM episodes").fetchone()
    assert row["utterance"] == "my debts?" and row["reply"] is None
    assert "12,431" not in "".join(str(v) for v in tuple(row))


# --- proposals -------------------------------------------------------------------------------------------------


def propose_tool(memory):
    (tool,) = memory.tools()
    assert tool.name == "propose_memory"
    return tool


async def test_a_proposal_is_inert_until_approved_then_recalled_as_approved(tmp_path):
    memory = make_memory(tmp_path)
    tool = propose_tool(memory)
    await memory.recall("anything")  # begins a turn
    reply = await tool.handler({"statement": "Rent clears on the 2nd of each month."}, ToolContext())
    assert "approves" in reply

    (p,) = memory.proposals()
    assert (p.status, p.source) == ("proposed", "inferred")
    assert await memory.recall("when does rent clear") == []  # not used before approval

    result = memory.approve(p.id)
    assert result is not None
    items = await memory.recall("when does rent clear")
    assert [i.source for i in items] == [SOURCE_USER_APPROVED]
    assert memory.get_memory(p.id).approved_by_user is True


async def test_a_rejected_proposal_is_not_recalled_or_reoffered(tmp_path):
    memory = make_memory(tmp_path)
    tool = propose_tool(memory)
    await memory.recall("x")
    await tool.handler({"statement": "Rent clears on the 2nd of each month."}, ToolContext())
    (p,) = memory.proposals()
    assert memory.reject(p.id) is True
    assert await memory.recall("when does rent clear") == []

    await memory.recall("later turn")
    again = await tool.handler({"statement": "Rent clears on the 2nd each month."}, ToolContext())
    assert "declined" in again
    assert memory.proposals() == []


async def test_a_proposal_made_with_tool_results_in_context_is_flagged(tmp_path):
    notices: list[str] = []
    memory = make_memory(tmp_path, FakeExtractor(), notices=notices)
    tool = propose_tool(memory)
    await memory.recall("x")
    await tool.handler({"statement": "Rent clears on the 2nd of each month."}, ToolContext(tool_results_in_context=True))
    await memory.record(__import__("sutra_orchestrator.memory", fromlist=["Episode"]).Episode("x", "y"))
    await memory.flush()

    (p,) = memory.proposals()
    assert p.tool_context is True
    assert "check it first" in notices[0]


async def test_the_proposal_cap_limits_stored_proposals_per_turn(tmp_path):
    memory = make_memory(tmp_path, proposal_cap=2)
    tool = propose_tool(memory)
    await memory.recall("x")
    suggestions = [
        "Prefers morning meetings over afternoon ones",
        "Plans a trip to Lisbon every spring",
        "Reviews investments on the first weekend monthly",
        "Walks the dog before breakfast",
    ]
    results = [await tool.handler({"statement": text}, ToolContext()) for text in suggestions]
    assert len(memory.proposals()) == 2
    assert all("too many" in r for r in results[2:])

    await memory.recall("a new turn")  # the cap resets each turn
    await tool.handler({"statement": "Yet another unrelated suggestion about travel."}, ToolContext())
    assert len(memory.proposals()) == 3


async def test_invalid_proposals_are_refused(tmp_path):
    memory = make_memory(tmp_path)
    tool = propose_tool(memory)
    await memory.recall("x")
    for args in ({}, {"statement": 5}, {"statement": "no"}, {"statement": "x" * 400}):
        assert (await tool.handler(args, ToolContext())).startswith("Not saved")
    assert memory.proposals() == []


async def test_a_proposal_that_duplicates_an_active_memory_is_refused(tmp_path):
    memory = make_memory(tmp_path)
    memory.add_memory("Rent clears on the 1st of each month")
    tool = propose_tool(memory)
    await memory.recall("x")
    reply = await tool.handler({"statement": "Rent clears on the 2nd of each month"}, ToolContext())
    assert "already known" in reply
    assert memory.proposals() == []


async def test_approving_a_proposal_supersedes_a_memory_it_contradicts(tmp_path):
    memory = make_memory(tmp_path)
    tool = propose_tool(memory)
    await memory.recall("x")
    await tool.handler({"statement": "Rent clears on the 2nd of each month"}, ToolContext())
    (proposal,) = memory.proposals()
    # The user states something close to it afterwards; the proposal itself is still inert.
    old = memory.add_memory("Rent clears on the 1st of each month").id
    assert memory.get_memory(old).status == "active"

    result = memory.approve(proposal.id)

    assert [r.id for r in result.replaced] == [old]
    assert memory.get_memory(old).status == "superseded"
    assert memory.get_memory(old).superseded_by == proposal.id
    assert memory.get_memory(proposal.id).status == "active"


# --- notices ---------------------------------------------------------------------------------------------------


async def test_notices_for_created_superseded_and_proposed_memories(tmp_path):
    notices: list[str] = []
    extractor = FakeExtractor(
        {
            "15th": [stmt("I get paid on the 15th.", "You get paid on the 15th.")],
            "1st": [stmt("I get paid on the 1st.", "You get paid on the 1st.")],
        }
    )
    memory = make_memory(tmp_path, extractor, notices=notices)

    await run_turn(memory, "I get paid on the 15th")
    assert notices == ["Noted: You get paid on the 15th."]

    await run_turn(memory, "I get paid on the 1st now")
    assert notices[-1] == "Updated: You get paid on the 1st. (replacing: You get paid on the 15th.)"

    tool = propose_tool(memory)
    await memory.recall("a turn with a proposal")
    await tool.handler({"statement": "Rent clears on the 2nd of each month."}, ToolContext())
    from sutra_orchestrator.memory import Episode

    await memory.record(Episode("a turn with a proposal", "ok"))
    await memory.flush()
    assert notices[-1].startswith("I'd like to remember that Rent clears on the 2nd of each month.")
    assert "/approve" in notices[-1] and "/reject" in notices[-1]


async def test_no_notice_when_nothing_changed(tmp_path):
    notices: list[str] = []
    memory = make_memory(tmp_path, FakeExtractor(), notices=notices)
    await run_turn(memory, "what's the weather")
    assert notices == []


async def test_a_failing_notice_callback_does_not_break_anything(tmp_path):
    def boom(_: str) -> None:
        raise RuntimeError("callback exploded")

    extractor = FakeExtractor({"15th": [stmt("I get paid on the 15th.")]})
    memory = make_memory(tmp_path, extractor)
    memory.set_notice_callback(boom)
    await run_turn(memory, "I get paid on the 15th")
    assert len(rows(memory)) == 1


# --- the archive ------------------------------------------------------------------------------------------------


async def test_old_episodes_move_to_the_archive_and_nothing_is_deleted(tmp_path):
    clock = Clock()
    extractor = FakeExtractor({"15th": [stmt("I get paid on the 15th.")]})
    memory = make_memory(tmp_path, extractor, clock)
    await run_turn(memory, "I get paid on the 15th", clock=clock)
    clock.advance(days=10)
    await run_turn(memory, "a recent message here", clock=clock)
    memory.close()

    clock.advance(days=25)  # the first is now 35 days old, the second 25
    reopened = make_memory(tmp_path, FakeExtractor(), clock)

    hot = [r["utterance"] for r in reopened._conn.execute("SELECT utterance FROM episodes")]
    assert hot == ["a recent message here"]
    archive = sqlite3.connect(tmp_path / "data" / "memory-archive.db")
    assert [r[0] for r in archive.execute("SELECT utterance FROM episodes")] == ["I get paid on the 15th"]
    # Memories never move or expire, however old.
    clock.advance(days=400)
    assert [i.content for i in await reopened.recall("when do I get paid")] == ["I get paid on the 15th."]


async def test_archived_episodes_never_reach_recall_the_extractor_or_any_prompt(tmp_path):
    clock = Clock()
    memory = make_memory(tmp_path, FakeExtractor(), clock, hot_days=1)
    await run_turn(memory, "SECRET-ARCHIVED-UTTERANCE about rent", reply="SECRET-ARCHIVED-REPLY", clock=clock)
    memory.close()
    clock.advance(days=5)

    extractor = FakeExtractor()
    fresh = make_memory(tmp_path, extractor, clock, hot_days=1)
    items = await fresh.recall("rent")
    await run_turn(fresh, "tell me about rent", clock=clock)

    assert items == []
    assert all("SECRET-ARCHIVED" not in c["user"] for c in extractor.calls)
    assert fresh._conn.execute("SELECT COUNT(*) FROM episodes WHERE utterance LIKE '%SECRET%'").fetchone()[0] == 0


async def test_recall_works_with_the_archive_file_missing_or_unreadable(tmp_path):
    clock = Clock()
    memory = make_memory(tmp_path, FakeExtractor(), clock, hot_days=1)
    memory.add_memory("Rent is due on the 1st.")
    await run_turn(memory, "old message", clock=clock)
    memory.close()
    clock.advance(days=5)
    fresh = make_memory(tmp_path, FakeExtractor(), clock, hot_days=1)  # archives it
    (tmp_path / "data" / "memory-archive.db").chmod(0o000)
    try:
        assert len(await fresh.recall("when is rent due")) == 1
        await run_turn(fresh, "another message", clock=clock)
    finally:
        (tmp_path / "data" / "memory-archive.db").chmod(0o600)


async def test_why_search_and_purge_work_on_the_archive(tmp_path):
    clock = Clock()
    extractor = FakeExtractor({"15th": [stmt("I get paid on the 15th.")]})
    memory = make_memory(tmp_path, extractor, clock, hot_days=1)
    await run_turn(memory, "I get paid on the 15th", reply="Noted.", clock=clock)
    clock.advance(days=3)
    await run_turn(memory, "newer conversation about budgets", clock=clock)
    memory.close()
    clock.advance(days=40)
    fresh = make_memory(tmp_path, FakeExtractor(), clock, hot_days=1)

    (m,) = [m for m in rows(fresh) if m.content.startswith("I get paid")]
    _, episode = fresh.why(m.id)
    assert episode.archived is True and episode.utterance == "I get paid on the 15th"

    assert [e.utterance for e in fresh.archive_search("budgets")] == ["newer conversation about budgets"]
    assert fresh.archive_search("nonexistent phrase") == []

    cutoff = (NOW + timedelta(days=1)).date()  # after the first episode, before the second
    assert fresh.archive_count_before(cutoff) == 1
    assert fresh.archive_purge(cutoff) == 1
    assert [e.utterance for e in fresh.archive_search("conversation")] == ["newer conversation about budgets"]
    assert fresh.archive_search("paid") == []
    assert fresh.archive_purge(date(2000, 1, 1)) == 0


async def test_nothing_is_deleted_automatically(tmp_path):
    clock = Clock()
    memory = make_memory(tmp_path, FakeExtractor(), clock, hot_days=1)
    for i in range(5):
        await run_turn(memory, f"message {i} about things", clock=clock)
        clock.advance(days=2)
    memory.close()
    fresh = make_memory(tmp_path, FakeExtractor(), clock, hot_days=1)
    hot = fresh._conn.execute("SELECT COUNT(*) FROM episodes").fetchone()[0]
    archived = sqlite3.connect(tmp_path / "data" / "memory-archive.db").execute(
        "SELECT COUNT(*) FROM episodes"
    ).fetchone()[0]
    assert hot + archived == 5


async def test_an_active_inferred_memory_the_user_never_approved_is_never_recalled(tmp_path):
    """Invariant for future code (e.g. reflection) that may create inferred memories:
    recall only ever serves what the user said or explicitly approved."""
    memory = make_memory(tmp_path)
    now = Clock()().isoformat()
    for source, approved in (("inferred", 0), ("tool_derived", 0)):
        cursor = memory._conn.execute(
            "INSERT INTO memories (kind, source, status, content, approved_by_user, created_at) "
            "VALUES ('fact', ?, 'active', 'Secret preference about rent timing', ?, ?)",
            (source, approved, now),
        )
        memory._conn.execute(
            "INSERT INTO memories_fts (rowid, content) VALUES (?, 'Secret preference about rent timing')",
            (cursor.lastrowid,),
        )
    memory._conn.commit()

    assert await memory.recall("rent timing") == []

    # Once the user approves one, it is served.
    memory._conn.execute("UPDATE memories SET approved_by_user = 1 WHERE source = 'inferred'")
    memory._conn.commit()
    items = await memory.recall("rent timing")
    assert [i.source for i in items] == [SOURCE_USER_APPROVED]
