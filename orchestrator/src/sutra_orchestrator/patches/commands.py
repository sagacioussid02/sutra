"""REPL commands for patch drafts: list, show, discard."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from .service import PatchService
from .store import PatchRow

OFF = "Patches are off. Set SUTRA_PATCHES=on to let me draft changes on a branch."
HELP = [
    "Patch commands:",
    "  /patches               recent drafts and today's usage",
    "  /patches show <id>     summary, files, test outcome, diff stat and branch",
    "  /patches discard <id>  remove a draft's worktree and branch",
    "  /patches discard all   remove every draft",
]


def _test_line(row: PatchRow) -> str:
    if row.test_status == "untested":
        return "not tested" + (f" ({row.test_detail})" if row.test_detail else "")
    return f"tests {row.test_status}"


class PatchCommands:
    def __init__(self, service: PatchService | None) -> None:
        self._service = service

    async def handle(self, line: str, read: Callable[[str], Awaitable[str]]) -> list[str] | None:
        line = line.strip()
        if not line.startswith("/"):
            return None
        command, _, rest = line[1:].partition(" ")
        if command.lower() != "patches":
            return None
        if self._service is None:
            return [OFF]
        words = rest.split()
        if not words:
            return self._overview()
        if words[0] == "show" and len(words) == 2 and words[1].isdigit():
            return self._show(int(words[1]))
        if words[0] == "discard" and len(words) == 2:
            if words[1] == "all":
                return [f"Discarded {self._service.discard_all()} draft(s)."]
            if words[1].isdigit():
                ok = self._service.discard(int(words[1]))
                return [f"Discarded draft #{words[1]}." if ok else f"No draft #{words[1]} to discard."]
        return HELP

    def _overview(self) -> list[str]:
        assert self._service is not None
        budget = self._service.budget
        runs, tokens = self._service.today_usage()
        lines = [f"Today: {runs} of {budget.daily_runs} runs, {tokens} of {budget.daily_tokens} tokens."]
        rows = self._service.store.list_patches(10)
        if not rows:
            return lines + ["No drafts yet."]
        for r in rows:
            note = f" ({r.reason})" if r.reason else ""
            branch = f" on {r.branch}" if r.branch and r.status in ("drafted", "partial") else ""
            lines.append(f"#{r.id} {r.status}{note}{branch}, {_test_line(r)}: {r.task}")
        return lines

    def _show(self, pid: int) -> list[str]:
        assert self._service is not None
        row = self._service.store.get(pid)
        if row is None or row.status == "discarded":
            return [f"No draft #{pid}."]
        lines = [f"Draft #{row.id}: {row.status}" + (f" ({row.reason})" if row.reason else ""), f"Asked: {row.task}"]
        if row.summary:
            lines += ["Its own summary (untrusted, not verified):", *("  > " + s for s in row.summary.splitlines())]
        if row.files:
            lines.append("Files: " + ", ".join(row.files))
        lines.append(f"Tests: {_test_line(row)}")
        if row.refusals:
            lines.append(f"Refused {row.refusals} attempt(s) at protected or out-of-bounds paths.")
        if row.diff_stat:
            lines += ["Changes:", *("  " + s for s in row.diff_stat.splitlines())]
        if row.branch and row.status in ("drafted", "partial"):
            lines += [
                f"Review: git diff main...{row.branch}",
                f"Merge (yours to do): git merge {row.branch}",
            ]
        return lines
