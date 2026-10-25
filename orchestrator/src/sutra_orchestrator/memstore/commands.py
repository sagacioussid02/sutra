"""REPL commands for inspecting and controlling memory.

Lines starting with ``/`` are handled here and never reach the model. Output is
shown to the user only.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import date, datetime, timezone

from .provider import EpisodeView, MemoryRow, SqliteMemory

FORGET_WORD = "FORGET"
PURGE_WORD = "PURGE"

HELP = [
    "Memory commands:",
    "  /memories [query]    list what I remember, or search it",
    "  /remember <text>     add something for me to remember",
    "  /forget <id>         delete one memory",
    "  /forget all          delete every memory (asks you to type FORGET)",
    "  /why <id>            show where a memory came from",
    "  /proposals           things I'd like to remember, waiting for your OK",
    "  /approve <id>        keep a proposal",
    "  /reject <id>         decline a proposal",
    "  /archive search <q>  search old conversations (older than the hot period)",
    "  /archive purge --before YYYY-MM-DD   permanently delete old conversations",
]

_SOURCES = {
    "user_stated": "you said it",
    "inferred": "I suggested it",
    "tool_derived": "from a tool",
}


def _age(then: datetime, now: datetime) -> str:
    days = max((now - then).days, 0)
    if days == 0:
        return "today"
    return f"{days} day{'s' if days != 1 else ''} ago"


def describe(memory: MemoryRow, now: datetime) -> str:
    source = _SOURCES.get(memory.source, memory.source)
    if memory.approved_by_user:
        source += ", you approved it"
    tag = ""
    if memory.status == "superseded":
        tag = f" (replaced by #{memory.superseded_by})" if memory.superseded_by else " (replaced)"
    elif memory.status != "active":
        tag = f" ({memory.status})"
    return f"#{memory.id} [{memory.kind}, {source}] {memory.content}{tag} - {_age(memory.created_at, now)}"


def _describe_episode(episode: EpisodeView) -> list[str]:
    where = "archived conversation" if episode.archived else "conversation"
    lines = [f"  From a {where} on {episode.ts.astimezone().strftime('%Y-%m-%d %H:%M')}:"]
    lines.append(f"    you said: {episode.utterance}")
    if episode.reply:
        lines.append(f"    I replied: {episode.reply}")
    if episode.tools:
        lines.append("    tools: " + ", ".join(f"{t['name']} ({t['status']})" for t in episode.tools))
    if episode.confirmation:
        lines.append(f"    confirmation: {episode.confirmation}")
    return lines


class MemoryCommands:
    def __init__(
        self, memory: SqliteMemory, *, now: Callable[[], datetime] | None = None
    ) -> None:
        self._memory = memory
        self._now = now or (lambda: datetime.now(timezone.utc))

    async def handle(
        self, line: str, read: Callable[[str], Awaitable[str]]
    ) -> list[str] | None:
        """Run a command. Returns the lines to show, or None if ``line`` is not a command."""
        line = line.strip()
        if not line.startswith("/"):
            return None
        command, _, rest = line[1:].partition(" ")
        rest = rest.strip()
        handler = {
            "memories": self._memories,
            "remember": self._remember,
            "forget": self._forget,
            "why": self._why,
            "proposals": self._proposals,
            "approve": self._approve,
            "reject": self._reject,
            "archive": self._archive,
            "help": self._help,
        }.get(command.lower())
        if handler is None:
            return [f"Unknown command /{command}. Type /help for the list."]
        return await handler(rest, read)

    # -- helpers ---------------------------------------------------------------

    @staticmethod
    def _parse_id(text: str) -> int | None:
        text = text.strip().lstrip("#")
        return int(text) if text.isdigit() else None

    # -- commands -----------------------------------------------------------------

    async def _help(self, rest, read) -> list[str]:
        return HELP

    async def _memories(self, rest, read) -> list[str]:
        now = self._now()
        rows = self._memory.search_memories(rest) if rest else self._memory.list_memories()
        if not rows:
            return ["No matching memories." if rest else "No memories yet."]
        return [describe(r, now) for r in rows]

    async def _remember(self, rest, read) -> list[str]:
        if not rest:
            return ["Usage: /remember <something for me to remember>"]
        result = self._memory.add_memory(rest)
        if result.id is None:
            return ["I already have that."]
        lines = [f"Remembered as #{result.id}."]
        for old in result.replaced:
            lines.append(f"This replaced #{old.id}: {old.content}")
        return lines

    async def _forget(self, rest, read) -> list[str]:
        if rest.lower() == "all":
            count = len(self._memory.list_memories())
            if count == 0:
                return ["There is nothing to forget."]
            answer = await read(f"This deletes all {count} memories. Type {FORGET_WORD} to confirm: ")
            if answer.strip() != FORGET_WORD:
                return ["Cancelled. Nothing was deleted."]
            return [f"Deleted {self._memory.forget_all()} memories."]
        memory_id = self._parse_id(rest)
        if memory_id is None:
            return ["Usage: /forget <id>, or /forget all"]
        if self._memory.delete_memory(memory_id):
            return [f"Forgot #{memory_id}."]
        return [f"There is no memory #{memory_id}."]

    async def _why(self, rest, read) -> list[str]:
        memory_id = self._parse_id(rest)
        if memory_id is None:
            return ["Usage: /why <id>"]
        found = self._memory.why(memory_id)
        if found is None:
            return [f"There is no memory #{memory_id}."]
        memory, episode = found
        lines = [describe(memory, self._now())]
        if memory.episode_id is None:
            lines.append("  You added this directly with /remember.")
        elif episode is None:
            lines.append("  The conversation it came from is no longer stored.")
        else:
            lines.extend(_describe_episode(episode))
        if memory.tool_context:
            lines.append("  Note: I suggested this while reading tool results, so check it.")
        return lines

    async def _proposals(self, rest, read) -> list[str]:
        proposals = self._memory.proposals()
        if not proposals:
            return ["No proposals waiting."]
        lines: list[str] = []
        now = self._now()
        for p in proposals:
            lines.append(describe(p, now))
            if p.tool_context:
                lines.append("  Heads up: suggested while reading tool results. Check it first.")
            lines.append(f"  /approve {p.id}   or   /reject {p.id}")
        return lines

    async def _approve(self, rest, read) -> list[str]:
        memory_id = self._parse_id(rest)
        if memory_id is None:
            return ["Usage: /approve <id>"]
        result = self._memory.approve(memory_id)
        if result is None:
            return [f"There is no waiting proposal #{memory_id}."]
        lines = [f"Approved. I'll remember #{memory_id}."]
        for old in result.replaced:
            lines.append(f"This replaced #{old.id}: {old.content}")
        return lines

    async def _reject(self, rest, read) -> list[str]:
        memory_id = self._parse_id(rest)
        if memory_id is None:
            return ["Usage: /reject <id>"]
        if self._memory.reject(memory_id):
            return [f"Declined #{memory_id}. I won't suggest it again."]
        return [f"There is no waiting proposal #{memory_id}."]

    async def _archive(self, rest, read) -> list[str]:
        sub, _, arg = rest.partition(" ")
        arg = arg.strip()
        if sub == "search":
            if not arg:
                return ["Usage: /archive search <text>"]
            found = self._memory.archive_search(arg)
            if not found:
                return ["Nothing in the archive matches."]
            lines: list[str] = []
            for episode in found:
                lines.extend(_describe_episode(episode))
            return lines
        if sub == "purge":
            flag, _, value = arg.partition(" ")
            try:
                if flag != "--before":
                    raise ValueError
                before = date.fromisoformat(value.strip())
            except ValueError:
                return ["Usage: /archive purge --before YYYY-MM-DD"]
            count = self._memory.archive_count_before(before)
            if count == 0:
                return ["No archived conversations are older than that."]
            answer = await read(
                f"This permanently deletes {count} archived conversations. "
                f"Type {PURGE_WORD} to confirm: "
            )
            if answer.strip() != PURGE_WORD:
                return ["Cancelled. Nothing was deleted."]
            return [f"Deleted {self._memory.archive_purge(before)} archived conversations."]
        return ["Usage: /archive search <text>   or   /archive purge --before YYYY-MM-DD"]
