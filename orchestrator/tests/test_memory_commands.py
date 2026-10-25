"""The /memories, /remember, /forget, /why, proposals and archive commands."""

from __future__ import annotations

from datetime import timedelta

from sutra_orchestrator.memory import ToolContext
from sutra_orchestrator.memstore.commands import MemoryCommands

from .fakes import Clock
from .memhelpers import FakeExtractor, make_memory, run_turn, stmt


class Typed:
    """A scripted `read` for confirmation prompts."""

    def __init__(self, *answers: str):
        self.answers = list(answers)
        self.prompts: list[str] = []

    async def __call__(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.answers.pop(0) if self.answers else ""


async def cmd(commands: MemoryCommands, line: str, *answers: str):
    return await commands.handle(line, Typed(*answers))


def setup(tmp_path, **kwargs):
    clock = Clock()
    memory = make_memory(tmp_path, kwargs.pop("extractor", FakeExtractor()), clock, **kwargs)
    return memory, MemoryCommands(memory, now=clock), clock


async def test_non_commands_are_not_handled(tmp_path):
    _, commands, _ = setup(tmp_path)
    assert await cmd(commands, "how much do I owe?") is None


async def test_unknown_commands_get_a_hint_and_never_reach_the_model(tmp_path):
    _, commands, _ = setup(tmp_path)
    out = await cmd(commands, "/memory")
    assert "Unknown command /memory" in out[0] and "/help" in out[0]
    assert any("/forget all" in line for line in await cmd(commands, "/help"))


async def test_listing_shows_newest_first_with_ids_kinds_sources_and_status(tmp_path):
    memory, commands, clock = setup(tmp_path)
    old = memory.add_memory("I get paid on the 15th").id
    clock.advance(days=3)
    new = memory.add_memory("I get paid on the 1st").id  # supersedes the first

    lines = await cmd(commands, "/memories")

    assert lines[0].startswith(f"#{new} [fact, you said it] I get paid on the 1st")
    assert lines[0].endswith("today")
    assert lines[1].startswith(f"#{old} [fact, you said it] I get paid on the 15th")
    assert f"(replaced by #{new})" in lines[1] and "3 days ago" in lines[1]


async def test_empty_listing_and_search(tmp_path):
    memory, commands, _ = setup(tmp_path)
    assert await cmd(commands, "/memories") == ["No memories yet."]
    memory.add_memory("Rent is due on the 1st")
    assert await cmd(commands, "/memories groceries") == ["No matching memories."]
    (hit,) = await cmd(commands, "/memories rent")
    assert "Rent is due on the 1st" in hit


async def test_remember_adds_a_user_stated_memory(tmp_path):
    memory, commands, _ = setup(tmp_path)
    out = await cmd(commands, "/remember I prefer metric units")
    (m,) = memory.list_memories()
    assert out == [f"Remembered as #{m.id}."]
    assert (m.content, m.source, m.status, m.episode_id) == ("I prefer metric units", "user_stated", "active", None)

    assert await cmd(commands, "/remember i prefer metric units.") == ["I already have that."]
    assert (await cmd(commands, "/remember")) == ["Usage: /remember <something for me to remember>"]


async def test_remember_reports_what_it_replaced(tmp_path):
    memory, commands, _ = setup(tmp_path)
    old = memory.add_memory("I get paid on the 15th").id
    out = await cmd(commands, "/remember I get paid on the 1st")
    assert any(f"replaced #{old}" in line for line in out)


async def test_forget_one(tmp_path):
    memory, commands, _ = setup(tmp_path)
    mid = memory.add_memory("Rent is due on the 1st").id
    assert await cmd(commands, f"/forget {mid}") == [f"Forgot #{mid}."]
    assert await cmd(commands, f"/forget #{mid}") == [f"There is no memory #{mid}."]
    assert await cmd(commands, "/forget banana") == ["Usage: /forget <id>, or /forget all"]
    assert memory.list_memories() == []


async def test_forget_all_needs_the_confirmation_word(tmp_path):
    memory, commands, _ = setup(tmp_path)
    memory.add_memory("Rent is due on the 1st")
    memory.add_memory("I prefer metric units")

    for wrong in ("", "yes", "forget", "FORGET please"):
        assert await cmd(commands, "/forget all", wrong) == ["Cancelled. Nothing was deleted."]
        assert len(memory.list_memories()) == 2

    reader = Typed("FORGET")
    out = await commands.handle("/forget all", reader)
    assert out == ["Deleted 2 memories."]
    assert "2 memories" in reader.prompts[0] and "FORGET" in reader.prompts[0]
    assert memory.list_memories() == []
    fts = memory._conn.execute("SELECT COUNT(*) FROM memories_fts").fetchone()[0]
    assert fts == 0


async def test_forget_all_with_nothing_stored(tmp_path):
    _, commands, _ = setup(tmp_path)
    assert await cmd(commands, "/forget all") == ["There is nothing to forget."]


async def test_why_shows_the_originating_conversation(tmp_path):
    extractor = FakeExtractor({"15th": [stmt("I get paid on the 15th.")]})
    memory, commands, clock = setup(tmp_path, extractor=extractor)
    await run_turn(memory, "I get paid on the 15th", reply="Noted.", clock=clock)
    (m,) = memory.list_memories()

    out = "\n".join(await cmd(commands, f"/why {m.id}"))

    assert "you said: I get paid on the 15th" in out and "I replied: Noted." in out
    assert "archived" not in out


async def test_why_for_directly_added_missing_and_invalid_ids(tmp_path):
    memory, commands, _ = setup(tmp_path)
    mid = memory.add_memory("Rent is due on the 1st").id
    assert any("added this directly" in line for line in await cmd(commands, f"/why {mid}"))
    assert await cmd(commands, "/why 999") == ["There is no memory #999."]
    assert await cmd(commands, "/why") == ["Usage: /why <id>"]


async def test_why_reads_the_archive_for_old_conversations(tmp_path):
    clock = Clock()
    extractor = FakeExtractor({"15th": [stmt("I get paid on the 15th.")]})
    memory = make_memory(tmp_path, extractor, clock, hot_days=1)
    await run_turn(memory, "I get paid on the 15th", clock=clock)
    memory.close()
    clock.advance(days=10)
    fresh = make_memory(tmp_path, FakeExtractor(), clock, hot_days=1)
    commands = MemoryCommands(fresh, now=clock)
    (m,) = fresh.list_memories()

    out = "\n".join(await cmd(commands, f"/why {m.id}"))

    assert "archived conversation" in out and "you said: I get paid on the 15th" in out


async def test_proposals_listing_approve_and_reject(tmp_path):
    memory, commands, _ = setup(tmp_path)
    (tool,) = memory.tools()
    await memory.recall("x")
    await tool.handler({"statement": "Rent clears on the 2nd of each month"}, ToolContext(tool_results_in_context=True))
    await tool.handler({"statement": "Prefers morning meetings over afternoon ones"}, ToolContext())
    first, second = memory.proposals()

    listing = "\n".join(await cmd(commands, "/proposals"))
    assert f"/approve {first.id}" in listing and "reading tool results" in listing
    assert listing.count("Heads up") == 1  # only the flagged one

    assert (await cmd(commands, f"/approve {first.id}"))[0].startswith("Approved")
    assert (await cmd(commands, f"/reject {second.id}"))[0].startswith("Declined")
    assert await cmd(commands, "/proposals") == ["No proposals waiting."]
    assert await cmd(commands, f"/approve {first.id}") == [f"There is no waiting proposal #{first.id}."]
    assert await cmd(commands, "/approve x") == ["Usage: /approve <id>"]
    assert await cmd(commands, "/reject") == ["Usage: /reject <id>"]

    listing = "\n".join(await cmd(commands, "/memories"))
    assert "you approved it" in listing and "(rejected)" in listing


async def test_archive_search_and_purge_with_confirmation(tmp_path):
    clock = Clock()
    memory = make_memory(tmp_path, FakeExtractor(), clock, hot_days=1)
    await run_turn(memory, "an old chat about mortgages", clock=clock)
    memory.close()
    clock.advance(days=10)
    fresh = make_memory(tmp_path, FakeExtractor(), clock, hot_days=1)
    commands = MemoryCommands(fresh, now=clock)

    found = "\n".join(await cmd(commands, "/archive search mortgages"))
    assert "an old chat about mortgages" in found
    assert await cmd(commands, "/archive search zebra") == ["Nothing in the archive matches."]

    cutoff = (clock() + timedelta(days=1)).date().isoformat()
    assert await cmd(commands, f"/archive purge --before {cutoff}", "nope") == [
        "Cancelled. Nothing was deleted."
    ]
    assert len(fresh.archive_search("mortgages")) == 1

    assert await cmd(commands, f"/archive purge --before {cutoff}", "PURGE") == [
        "Deleted 1 archived conversations."
    ]
    assert fresh.archive_search("mortgages") == []
    assert await cmd(commands, f"/archive purge --before {cutoff}") == [
        "No archived conversations are older than that."
    ]
    assert "Usage" in (await cmd(commands, "/archive purge --before tomorrow"))[0]
    assert "Usage" in (await cmd(commands, "/archive"))[0]
