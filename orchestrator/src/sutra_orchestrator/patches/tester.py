"""Run a draft's tests under an OS sandbox, or not at all.

Generated code never runs unconfined. ``sandbox-exec`` (macOS) or ``bwrap`` (Linux) gives the test
process no network, writes only inside the worktree and a private temp directory, and a scrubbed
environment (no keys, no ``.env``). With neither present nothing is run and the draft is untested.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import shutil
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

NO_SANDBOX = "no sandbox available"
TAIL_CHARS = 1500

# Outcomes: passed, failed, timeout, untested.


@dataclass(frozen=True)
class TestOutcome:
    __test__ = False  # not a pytest class

    status: str
    detail: str = ""


def detect() -> str | None:
    if sys.platform == "darwin" and shutil.which("sandbox-exec"):
        return "sandbox-exec"
    if sys.platform.startswith("linux") and shutil.which("bwrap"):
        return "bwrap"
    return None


def _scrubbed_env(root: Path, tmp: Path, project_dir: Path) -> dict[str, str]:
    path = os.pathsep.join(
        dict.fromkeys([str(Path(sys.executable).parent), "/usr/local/bin", "/usr/bin", "/bin"])
    )
    return {
        "PATH": path,
        "HOME": str(tmp),
        "TMPDIR": str(tmp),
        "LANG": "C.UTF-8",
        "PYTHONPATH": str(project_dir / "src"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONNOUSERSITE": "1",
        "PYTEST_ADDOPTS": "-p no:cacheprovider",
    }


def _macos_profile(root: Path, tmp: Path) -> str:
    for p in (root, tmp):
        if '"' in str(p) or "\\" in str(p):
            raise ValueError("unsafe path for sandbox profile")
    return (
        "(version 1)(allow default)(deny network*)"
        "(deny file-write*)"
        f'(allow file-write* (subpath "{root}") (subpath "{tmp}") (literal "/dev/null") (literal "/dev/dtracehelper"))'
        '(deny file-read* (regex #"/\\.env[^/]*$"))'
    )


def _wrap(kind: str, root: Path, tmp: Path, cwd: Path, argv: list[str]) -> list[str]:
    if kind == "sandbox-exec":
        return ["sandbox-exec", "-p", _macos_profile(root, tmp), *argv]
    return [
        "bwrap", "--ro-bind", "/", "/", "--dev", "/dev", "--proc", "/proc",
        "--bind", str(root), str(root), "--bind", str(tmp), str(tmp),
        "--unshare-net", "--unshare-pid", "--die-with-parent", "--chdir", str(cwd), *argv,
    ]


async def run_tests(
    root: Path, command: list[str], project_dir: Path, timeout_s: float, *, kind: str | None = None
) -> TestOutcome:
    """Run ``command`` in ``project_dir`` (inside ``root``) under the sandbox."""
    kind = kind or detect()
    if kind is None:
        return TestOutcome("untested", NO_SANDBOX)
    root = root.resolve()
    project_dir = project_dir.resolve()
    if root != project_dir and root not in project_dir.parents:
        return TestOutcome("untested", "test directory is outside the draft")
    tmp = Path(tempfile.mkdtemp(prefix="sutra-patch-")).resolve()
    try:
        argv = [sys.executable if command[0] == "python" else command[0], *command[1:]]
        proc = await asyncio.create_subprocess_exec(
            *_wrap(kind, root, tmp, project_dir, argv),
            cwd=project_dir,
            env=_scrubbed_env(root, tmp, project_dir),
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            start_new_session=True,
        )
        try:
            out, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout_s)
        except asyncio.TimeoutError:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(proc.pid, 9)
            await proc.wait()
            return TestOutcome("timeout", f"stopped after {int(timeout_s)} seconds")
        except asyncio.CancelledError:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(proc.pid, 9)
            raise
        text = out.decode("utf-8", "replace").strip()
        return TestOutcome("passed" if proc.returncode == 0 else "failed", text[-TAIL_CHARS:])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
