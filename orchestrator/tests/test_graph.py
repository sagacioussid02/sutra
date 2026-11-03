"""Episode graph: nodes from conversations, validated links, retrieval, advice, decay."""

from __future__ import annotations

import os
import stat
from datetime import timedelta
from typing import Any

import pytest

from sutra_orchestrator.graph import GraphCommands, GraphService, GraphStore, LexicalRetriever
from sutra_orchestrator.graph import store as graph_store
from sutra_orchestrator.graph.service import IDLE_MINUTES

from .fakes import NOW, Clock


class FakeStructured:
    """A StructuredModel scripted per schema name: a list (popped in order) or a callable."""

    def __init__(self, **scripts: Any) -> None:
        self.scripts = {k: (list(v) if isinstance(v, list) else v) for k, v in scripts.items()}
        self.calls: list[dict[str, str]] = []

    def count(self, name: str) -> int:
        return sum(1 for c in self.calls if c["name"] == name)

    async def structured(self, *, name: str, system: str, user: str) -> dict[str, Any]:
        self.calls.append({"name": name, "system": system, "user": user})
        script = self.scripts.get(name)
        if script is None:
            raise AssertionError(f"unscripted structured call: {name}")
        item = script.pop(0) if isinstance(script, list) else script
        if isinstance(item, Exception):
            raise item
        return item(user) if callable(item) else item


def episode(topic="how tool calling works", gist="A model asks the program to run a function.", **kw):
    return {
        "keep": True,
        "topic": topic,
        "gist": gist,
        "mode": "explained",
        "open": ["example", "deeper"],
        "entities": ["tool calling", "function"],
        **kw,
    }


def make(tmp_path, model=None, clock=None, **kw):
    clock = clock or Clock()
    store = GraphStore(tmp_path)
    model = model or FakeStructured(episode=[episode()], links=[{"edges": []}])
    service = GraphService(store, model, now=clock, **kw)
    return store, model, service, clock


async def talk(service, clock, *turns, tools=()):
    for user, reply in turns:
        service.observe(user, reply, list(tools))
        clock.advance(seconds=20)
    service.close_episode()
    await service.flush()


# ----------------------------------------------------------------- episodes


async def test_explanation_becomes_a_node_without_storing_the_words(tmp_path):
    store, model, service, clock = make(tmp_path)
    await talk(service, clock, ("how does tool calling work in an AI model", "The model asks your code to run a function."))
    [node] = store.list()
    assert node.topic == "how tool calling works" and "example" in node.open
    assert node.mode == "explained"
    # Neither the utterance nor the reply is kept, only the summary.
    raw = open(tmp_path / "graph.db", "rb").read()
    assert b"how does tool calling work in an AI model" not in raw
    assert b"asks your code to run" not in raw
    assert stat.S_IMODE(os.stat(tmp_path / "graph.db").st_mode) == 0o600
    # The model saw the reply on a no-tool turn.
    assert "Assistant: The model asks your code" in model.calls[0]["user"]


async def test_excluded_tool_turns_contribute_nothing_and_tool_turns_count_only_the_user(tmp_path):
    store, model, service, clock = make(tmp_path)
    service.observe("what is my debt balance right now", "It is 3000.", ["finanxe_list_debts"])
    service.close_episode()
    await service.flush()
    assert model.calls == [] and store.list() == []

    service.observe("research the best hiking boots for me", "Researched answer text.", ["web_lookup"])
    service.close_episode()
    await service.flush()
    sent = model.calls[0]["user"]
    assert "hiking boots" in sent and "Researched answer text" not in sent


async def test_low_confidence_chores_and_small_talk_are_not_observed(tmp_path):
    store, model, service, clock = make(tmp_path)
    service.observe("how does tool calling work", "x", [], low_confidence=True)
    service.observe("yes", "x", [])
    service.close_episode()
    await service.flush()
    assert model.calls == []


async def test_not_worth_keeping_and_model_failure_leave_no_node(tmp_path):
    model = FakeStructured(episode=[{"keep": False}, RuntimeError("boom")])
    store, model, service, clock = make(tmp_path, model)
    await talk(service, clock, ("set a reminder to call mom tomorrow", "Done."))
    await talk(service, clock, ("how does tool calling work in practice", "Like this."))
    assert store.list() == []


async def test_subject_change_and_idle_gap_close_the_episode(tmp_path):
    model = FakeStructured(
        episode=[episode(), episode("weekend hiking trip", "Plans for a hike.")],
        links=lambda user: {"edges": []},
    )
    store, model, service, clock = make(tmp_path, model)
    service.observe("how does tool calling work in a model", "It runs functions.", [])
    clock.advance(seconds=30)
    service.observe("tool calling returns results to the model", "Yes.", [])  # same subject: no close
    assert model.count("episode") == 0
    clock.advance(seconds=30)
    service.observe("where should we hike this weekend near Denver", "Try Mount Falcon.", [])  # new subject
    clock.advance(minutes=IDLE_MINUTES + 1)
    service.observe("what trails have good views of mountains", "Many.", [])  # idle gap
    await service.flush()
    assert model.count("episode") == 2


# ----------------------------------------------------------------- linking


async def test_related_episode_is_linked_with_a_reason_and_invalid_edges_are_dropped(tmp_path):
    first = episode()
    second = episode("building a small agent", "Structure for a small AI agent.", open=["practice"])
    links = {
        "edges": [
            {"target": 1, "type": "applies_to", "strength": 0.7, "reason": "The agent uses tool calling."},
            {"target": 9, "type": "extends", "strength": 0.9, "reason": "Not a candidate."},
            {"target": 1, "type": "bogus", "strength": 0.9, "reason": "Unknown type."},
        ]
    }
    model = FakeStructured(episode=[first, second], links=[links])
    store, model, service, clock = make(tmp_path, model)
    await talk(service, clock, ("how does tool calling work in a model", "It runs functions."))
    assert model.count("links") == 0  # nothing earlier to link to: no call
    clock.advance(days=1)
    await talk(service, clock, ("help me structure a small AI agent with tool calling", "Use a loop."))
    old = next(n for n in store.list() if n.topic == "how tool calling works")
    new = next(n for n in store.list() if n.topic == "building a small agent")
    [edge] = store.edges_of(new.id)
    assert (edge.a, edge.b, edge.type) == (new.id, old.id, "applies_to")
    assert edge.reason == "The agent uses tool calling."


async def test_repeating_a_question_merges_into_one_node(tmp_path):
    again = episode(gist="Updated: functions are described to the model by schema.", open=["deeper"])
    links = {"edges": [{"target": 1, "type": "same_topic", "strength": 0.9, "reason": "Same question again."}]}
    model = FakeStructured(episode=[episode(), again], links=[links])
    store, model, service, clock = make(tmp_path, model)
    await talk(service, clock, ("how does tool calling work in a model", "It runs functions."))
    clock.advance(days=2)
    await talk(service, clock, ("explain tool calling in a model again", "Schemas."))
    [node] = store.list()
    assert "schema" in node.gist and node.open == ("deeper",)
    assert store.count() == 1


# --------------------------------------------------------------- retrieval


def seed(store, clock, topic, gist, entities, open_items=("example",), days=1):
    return store.add_node(topic, gist, "explained", list(open_items), list(entities), clock() - timedelta(days=days))


def test_retriever_matches_words_widens_by_neighbours_and_falls_back_to_recent_open(tmp_path):
    store, _, _, clock = make(tmp_path)
    a = seed(store, clock, "how tool calling works", "functions called by a model", ["tool calling"], days=1)
    b = seed(store, clock, "python decorators", "wrapping functions", ["decorators"], open_items=(), days=2)
    c = seed(store, clock, "sourdough baking", "starter and flour", ["sourdough"], open_items=(), days=20)
    store.add_edge(a, b, "extends", 0.8, "related", clock())
    r = LexicalRetriever(store)
    hits = r.candidates("my tool calling code fails", now=clock())
    assert hits[0].node.id == a and hits[0].via == "lexical"
    via = {h.node.id: h.via for h in hits}
    assert via[b] == "neighbour"  # linked to a recently touched node
    assert c not in via  # unrelated, nothing open
    assert r.candidates("weather", now=clock(), lexical_only=True) == []
    # No lexical match at all: recent nodes with something open are still proposed to the judges.
    lone, _, _, clock2 = make(tmp_path / "lone")
    only = seed(lone, clock2, "how tool calling works", "functions", ["tool calling"], days=1)
    other = LexicalRetriever(lone).candidates("building an agent with an llm", now=clock2())
    assert [(h.node.id, h.via) for h in other] == [(only, "recent")]


def test_check_candidates_runs_once_per_subject_and_skips_the_current_conversation(tmp_path):
    store, _, service, clock = make(tmp_path)
    seed(store, clock, "how tool calling works", "functions called by a model", ["tool calling"], days=1)
    fresh = store.add_node("tool calling demo", "talked a minute ago", "worked_on", ["example"], ["tool calling"], clock())
    first = service.check_candidates("my tool calling loop never ends")
    assert first and fresh not in {c.node.id for c in first}
    assert service.check_candidates("my tool calling loop never ends again") == []  # same subject
    assert service.check_candidates("anything goes here today", low_confidence=True) == []
    assert service.check_candidates("ok") == []  # too little content


# ------------------------------------------------------------------ advice


async def test_advice_is_validated(tmp_path):
    model = FakeStructured(
        advice=[
            {"choice": 1, "benefit": 0.9, "reason": "They are building with it.", "step": "example"},
            {"choice": 0},
            {"choice": 7, "benefit": 1, "reason": "x", "step": "example"},
            {"choice": 1, "benefit": 5, "reason": "x", "step": "weird"},
        ]
    )
    store, model, service, clock = make(tmp_path, model)
    seed(store, clock, "how tool calling works", "functions called by a model", ["tool calling"])
    cands = service.check_candidates("my tool calling loop never ends")
    a = await service.advise("my tool calling loop never ends", cands, {})
    assert a and a.node.topic == "how tool calling works" and a.step == "example" and a.benefit == 0.9
    assert await service.advise("q", cands) is None  # none
    assert await service.advise("q", cands) is None  # a number that was not offered
    clamped = await service.advise("q", cands)
    assert clamped and clamped.benefit == 1.0 and clamped.step == "none"
    assert await service.advise("q", []) is None
    assert model.count("advice") == 4  # no call without candidates


# ------------------------------------------------------------ decay, forget


def test_nodes_fade_get_archived_and_are_no_longer_retrieved(tmp_path):
    store, _, service, clock = make(tmp_path)
    nid = seed(store, clock, "how tool calling works", "functions", ["tool calling"], days=1)
    assert store.decay(clock()) == (0, 0)
    later = clock() + timedelta(days=graph_store.HALF_LIFE_DAYS * 4)
    assert store.decay(later)[0] == 1
    assert store.get(nid).status == "archived"
    assert LexicalRetriever(store).candidates("tool calling", now=later) == []
    store.touch(nid, later)
    assert store.get(nid).status == "active"


def test_size_rail_deletes_weakest_archived_first(tmp_path, monkeypatch):
    monkeypatch.setattr(graph_store, "MAX_NODES", 2)
    store, _, _, clock = make(tmp_path)
    old = seed(store, clock, "old one", "a", [], days=1)
    store.add_node("two", "b", "asked", [], [], clock())
    store.add_node("three", "c", "asked", [], [], clock())
    with store._conn:
        store._conn.execute("UPDATE nodes SET status = 'archived' WHERE id = ?", (old,))
    store.decay(clock())
    assert store.get(old) is None and store.count() == 2


async def test_commands_list_show_why_and_forget(tmp_path):
    store, _, service, clock = make(tmp_path)
    a = seed(store, clock, "how tool calling works", "functions called by a model", ["tool calling"])
    b = seed(store, clock, "building an agent", "loop and tools", ["agent"])
    store.add_edge(b, a, "applies_to", 0.7, "The agent uses tool calling.", clock())
    cmds = GraphCommands(service)
    listing = await cmds.handle("/graph", None)
    assert any("how tool calling works" in line for line in listing)
    shown = await cmds.handle(f"/graph {b}", None)
    assert any("applies_to" in line and "The agent uses tool calling." in line for line in shown)
    assert await cmds.handle(f"/graph forget {a}", None) == [f"Deleted #{a}."]
    assert store.edges_of(b) == []  # its links went with it
    assert (await cmds.handle("/graph forget all", None))[0].startswith("Deleted 1")
    assert await cmds.handle("/other", None) is None


def test_a_newer_schema_is_refused_unmodified(tmp_path):
    from sutra_orchestrator.graph import GraphSchemaError

    GraphStore(tmp_path).close()
    import sqlite3

    conn = sqlite3.connect(tmp_path / "graph.db")
    conn.execute("PRAGMA user_version = 99")
    conn.commit()
    conn.close()
    with pytest.raises(GraphSchemaError):
        GraphStore(tmp_path)
