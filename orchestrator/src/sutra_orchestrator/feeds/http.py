"""A small, guarded fetch for the feeds. Standard library only; a failure is just None."""

from __future__ import annotations

import asyncio
import logging
import urllib.request
from collections.abc import Awaitable, Callable

log = logging.getLogger("sutra_orchestrator")

USER_AGENT = "sutra-assistant/0.1 (personal assistant; contact: owner)"
MAX_BYTES = 1_000_000
Fetch = Callable[[str], Awaitable[str | None]]


def _get(url: str, timeout: float) -> str | None:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 (fixed https hosts)
        return response.read(MAX_BYTES).decode("utf-8", errors="replace")


async def fetch_text(url: str, timeout: float = 10.0) -> str | None:
    """The body of a page, or None if anything went wrong. Never raises."""
    if not url.startswith("https://"):
        return None
    try:
        return await asyncio.to_thread(_get, url, timeout)
    except Exception as exc:
        log.debug("feed fetch failed (%s)", type(exc).__name__)
        return None
