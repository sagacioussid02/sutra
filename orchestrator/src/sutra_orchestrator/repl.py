"""Terminal REPL: a thin loop over ``Orchestrator.respond``."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

from .memstore.commands import MemoryCommands
from .orchestrator import Orchestrator


class SecretFilter(logging.Filter):
    """Redact known secrets from every log record, as a backstop."""

    def __init__(self, secrets: list[str]) -> None:
        super().__init__()
        self._secrets = [s for s in secrets if s]

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        for secret in self._secrets:
            message = message.replace(secret, "[redacted]")
        record.msg, record.args = message, None
        return True


def configure_logging(verbose: bool, secrets: list[str]) -> None:
    logger = logging.getLogger("sutra_orchestrator")
    logger.handlers.clear()
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("  [%(levelname)s] %(message)s"))
    handler.addFilter(SecretFilter(secrets))
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG if verbose else logging.WARNING)
    logger.propagate = False


async def _read_line(prompt: str) -> str:
    return await asyncio.to_thread(input, prompt)


async def run_repl(
    orchestrator: Orchestrator,
    *,
    read: Callable[[str], Awaitable[str]] = _read_line,
    out: Callable[[str], None] = print,
    commands: MemoryCommands | None = None,
) -> None:
    """Read typed turns until a blank line or end of input, then return.

    Lines starting with ``/`` go to ``commands`` (memory controls), never to the model.
    """
    shown_pending: str | None = None
    while True:
        try:
            line = await read("you> ")
        except (EOFError, KeyboardInterrupt):
            break
        text = line.strip()
        if not text:
            break
        if commands is not None and text.startswith("/"):
            for line_out in await commands.handle(text, read) or []:
                out(f"  {line_out}")
            continue
        reply = await orchestrator.respond(text)
        out(f"sutra> {reply}")
        # Memory notices ("Noted: ...") arrive from background extraction; wait
        # for them here so they print right after the reply, before the prompt.
        await orchestrator.flush()

        pending = orchestrator.pending
        if pending is not None and pending.pending_id != shown_pending:
            shown_pending = pending.pending_id
            out(f"  pending: {pending.description}")
            out(f"  expires: {pending.expires_at.astimezone().strftime('%H:%M:%S')}")
