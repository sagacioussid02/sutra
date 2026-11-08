"""A draft's git worktree: created off ``main``, confined file access, and the final diff check.

The running checkout is never written. Every drafter path is worktree-relative, is resolved
(symlinks included) and must stay inside the worktree, and a write must also clear the protected
list. All git work goes through ``git`` with hooks disabled.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from ..errors import OrchestratorError
from .protected import is_protected, is_secret, normalize

MAX_READ_CHARS = 20_000
MAX_WRITE_CHARS = 60_000
MAX_FILES = 12
SYMLINK_MODE = "120000"
BASE_REF = "main"

_GIT = ["git", "-c", "core.hooksPath=/dev/null", "-c", "commit.gpgsign=false"]


class PatchError(OrchestratorError):
    """A draft could not be set up or finished."""


class Refused(Exception):
    """A drafter action was refused. The message is safe to show the model."""


def git(cwd: Path, *args: str, check: bool = True) -> str:
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    proc = subprocess.run(  # noqa: S603 - fixed argv, no shell
        [*_GIT, *args], cwd=cwd, capture_output=True, text=True, env=env, timeout=60
    )
    if check and proc.returncode != 0:
        raise PatchError(f"git {args[0]} failed: {proc.stderr.strip()[:300]}")
    return proc.stdout


@dataclass(frozen=True)
class DiffEntry:
    status: str
    path: str
    new_mode: str


class Workspace:
    def __init__(self, repo: Path, root: Path, branch: str, base: str) -> None:
        self.repo = repo
        self.root = root
        self.branch = branch
        self.base = base
        self.refusals = 0
        self.written: set[str] = set()

    # ------------------------------------------------------------ lifecycle

    @classmethod
    def create(cls, repo: Path, base_dir: Path, ident: str) -> "Workspace":
        repo = repo.resolve()
        base_dir.mkdir(parents=True, exist_ok=True)
        root = base_dir.resolve() / ident
        if root == repo or repo in root.parents:
            raise PatchError("Drafts must live outside the running checkout.")
        branch = f"sutra/patch-{ident}"
        base = git(repo, "rev-parse", BASE_REF).strip()
        git(repo, "worktree", "add", "-q", str(root), "-b", branch, BASE_REF)
        return cls(repo, root.resolve(), branch, base)

    @classmethod
    def attach(cls, repo: Path, base_dir: Path, ident: str) -> "Workspace":
        """The handle for an existing draft, to remove it later."""
        repo = repo.resolve()
        return cls(repo, base_dir.resolve() / ident, f"sutra/patch-{ident}", "")

    def remove(self) -> None:
        """Delete the worktree and branch. Safe to call twice."""
        git(self.repo, "worktree", "remove", "--force", str(self.root), check=False)
        shutil.rmtree(self.root, ignore_errors=True)
        git(self.repo, "worktree", "prune", check=False)
        git(self.repo, "branch", "-D", self.branch, check=False)

    # ------------------------------------------------------------ confined files

    def _resolve(self, rel: str) -> tuple[str, Path]:
        clean = normalize(rel)
        if clean is None or ".git" in (p.lower() for p in clean.split("/")):
            self.refusals += 1
            raise Refused("That path isn't allowed.")
        target = (self.root / clean).resolve()
        if target != self.root and self.root not in target.parents:
            self.refusals += 1
            raise Refused("That path is outside the draft.")
        return clean, target

    def read_file(self, rel: str) -> str:
        clean, target = self._resolve(rel)
        if is_secret(clean):
            self.refusals += 1
            raise Refused("That file can't be read.")
        if not target.is_file():
            raise Refused("No such file.")
        text = target.read_text(encoding="utf-8", errors="replace")
        if len(text) > MAX_READ_CHARS:
            return text[:MAX_READ_CHARS] + "\n[truncated]"
        return text

    def write_file(self, rel: str, content: str) -> str:
        clean, target = self._resolve(rel)
        if is_protected(clean):
            self.refusals += 1
            raise Refused("That path is protected and can't be changed.")
        if not isinstance(content, str) or len(content) > MAX_WRITE_CHARS:
            raise Refused("The file is too large.")
        if clean not in self.written and len(self.written) >= MAX_FILES:
            raise Refused("Too many files in one draft.")
        if target.is_symlink() or target.is_dir():
            self.refusals += 1
            raise Refused("That path isn't allowed.")
        target.parent.mkdir(parents=True, exist_ok=True)
        # A directory made just now could itself have been a link out: check where it landed.
        parent = target.parent.resolve()
        if parent != self.root and self.root not in parent.parents:
            self.refusals += 1
            raise Refused("That path is outside the draft.")
        target.write_text(content, encoding="utf-8")
        self.written.add(clean)
        return f"Wrote {clean}."

    # ------------------------------------------------------------ the end-of-run check

    def stage_and_diff(self) -> list[DiffEntry]:
        """Stage everything and list the change against the base, one entry per path.

        Renames are reported as a delete plus an add so both ends are checked.
        """
        git(self.root, "add", "-A")
        raw = git(self.root, "diff", "--cached", "--raw", "--no-renames", "-z", self.base)
        fields = raw.split("\x00")
        entries: list[DiffEntry] = []
        i = 0
        while i + 1 < len(fields) and fields[i].startswith(":"):
            meta = fields[i].split()
            entries.append(DiffEntry(status=meta[4][0], path=fields[i + 1], new_mode=meta[1]))
            i += 2
        return entries

    @staticmethod
    def violations(entries: list[DiffEntry]) -> list[str]:
        bad: list[str] = []
        for e in entries:
            if is_protected(e.path):
                bad.append(e.path)
            elif e.new_mode == SYMLINK_MODE:
                bad.append(f"{e.path} (symbolic link)")
        return bad

    def commit(self, message: str) -> None:
        git(
            self.root, "-c", "user.name=Sutra", "-c", "user.email=sutra@localhost",
            "commit", "-q", "--no-verify", "-m", message,
        )

    def diff_stat(self) -> str:
        return git(self.repo, "diff", "--stat", f"{BASE_REF}...{self.branch}", check=False).strip()
