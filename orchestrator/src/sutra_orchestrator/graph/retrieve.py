"""Retrieval: propose candidate nodes for a piece of text. Models judge them.

The lexical retriever matches words, widens by graph neighbours of recently
touched nodes, and adds a few recent nodes that still have something open,
because word overlap alone misses "tool calling" versus "building an agent".
It only proposes. Anything fancier (embeddings) replaces this class and nothing
else: ``Retriever`` is the seam.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol

from ..memstore.textutil import tokens
from .store import GraphStore, Node

MAX_CANDIDATES = 8  # bounded by prompt size
RECENT_NEIGHBOUR_DAYS = 3
MAX_RECENT_OPEN = 3


@dataclass(frozen=True)
class Candidate:
    node: Node
    score: float
    via: str  # "lexical", "neighbour" or "recent"


class Retriever(Protocol):
    def candidates(
        self,
        text: str,
        *,
        now: datetime,
        exclude_touched_after: datetime | None = None,
        lexical_only: bool = False,
        limit: int = MAX_CANDIDATES,
    ) -> list[Candidate]: ...


# Summaries are written as "the person asked ... the assistant explained ...", so these words
# are in nearly every node and would match nearly every query.
_GENERIC = frozenset({"person", "assistant", "asked", "explained", "suggested", "said", "user"})


def _node_tokens(node: Node) -> set[str]:
    return set(tokens(" ".join([node.topic, node.gist, *node.entities]))) - _GENERIC


class LexicalRetriever:
    def __init__(self, store: GraphStore) -> None:
        self._store = store

    def candidates(
        self,
        text: str,
        *,
        now: datetime,
        exclude_touched_after: datetime | None = None,
        lexical_only: bool = False,
        limit: int = MAX_CANDIDATES,
    ) -> list[Candidate]:
        query = set(tokens(text)) - _GENERIC
        nodes = [
            n
            for n in self._store.list()
            if exclude_touched_after is None or n.last_touched <= exclude_touched_after
        ]
        found: dict[int, Candidate] = {}

        for node in nodes:
            shared = query & _node_tokens(node)
            entity_hit = shared & set(tokens(" ".join(node.entities)))
            if len(shared) >= 2 or entity_hit:
                score = len(shared) / max(1, min(len(query), len(_node_tokens(node))))
                found[node.id] = Candidate(node, score + 0.1 * node.live_weight(now), "lexical")

        if not lexical_only:
            by_id = {n.id: n for n in nodes}
            recent = now - timedelta(days=RECENT_NEIGHBOUR_DAYS)
            for node in nodes:
                if node.last_touched < recent:
                    continue
                for edge in self._store.edges_of(node.id):
                    other = by_id.get(edge.other(node.id))
                    if other is not None and other.id not in found:
                        found[other.id] = Candidate(other, 0.3 * edge.strength * edge.weight, "neighbour")
            fallbacks = [n for n in nodes if n.open and n.id not in found][:MAX_RECENT_OPEN]
            for node in fallbacks:  # nodes are newest-first
                found[node.id] = Candidate(node, 0.05, "recent")

        ranked = sorted(found.values(), key=lambda c: c.score, reverse=True)
        return ranked[:limit]
