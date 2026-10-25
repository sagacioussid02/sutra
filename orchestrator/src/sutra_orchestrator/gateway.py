"""Client side of the Sutra gateway: an MCP session plus result parsing."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Iterator
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal, Protocol

import anyio
import httpx2
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.shared.exceptions import MCPError
from mcp.types import CONNECTION_CLOSED

from .errors import GatewayAuthError, GatewayUnreachableError

log = logging.getLogger("sutra_orchestrator")

# The gateway's built-in confirmation tool. Only the orchestrator's
# confirmation gate may call it; it is never offered to the model.
CONFIRM_TOOL = "gateway_confirm"

# Gateway error text is passed to the model so it can phrase a failure; cap it
# so a huge error body cannot bloat the context.
_MAX_ERROR_CHARS = 400


@dataclass(frozen=True)
class ToolDef:
    name: str
    description: str
    input_schema: dict[str, Any]


@dataclass(frozen=True)
class PendingInfo:
    pending_id: str
    description: str
    expires_at: datetime


@dataclass(frozen=True)
class ToolResult:
    kind: Literal["ok", "pending", "error"]
    # ok: the (possibly truncated) JSON text; error: a short message.
    text: str = ""
    pending: PendingInfo | None = None
    # For errors: "unauthorized" | "disconnected" | "other".
    category: str | None = None
    truncated: bool = False


class GatewaySession(Protocol):
    async def list_tools(self) -> list[ToolDef]: ...

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> ToolResult: ...

    async def close(self) -> None: ...


def truncate_text(text: str, max_bytes: int) -> tuple[str, bool]:
    """Cut ``text`` to at most ``max_bytes`` UTF-8 bytes, with an explicit marker."""
    raw = text.encode("utf-8")
    if len(raw) <= max_bytes:
        return text, False
    kept = raw[:max_bytes].decode("utf-8", errors="ignore")
    marker = f"\n[truncated: result was {len(raw)} bytes, showing the first {len(kept.encode())}]"
    return kept + marker, True


def _parse_pending(data: Any) -> PendingInfo | None:
    if not isinstance(data, dict):
        return None
    pid, desc, exp = data.get("pending_id"), data.get("description"), data.get("expires_at")
    if not (isinstance(pid, str) and isinstance(desc, str) and isinstance(exp, str)):
        return None
    try:
        expires = datetime.fromisoformat(exp)
    except ValueError:
        return None
    if expires.tzinfo is None:
        return None
    return PendingInfo(pending_id=pid, description=desc, expires_at=expires)


def parse_tool_result(text: str, is_error: bool, max_bytes: int) -> ToolResult:
    """Classify a raw gateway tool result as ok, pending, or error."""
    if is_error:
        category = "unauthorized" if "not authorized" in text else "other"
        return ToolResult(kind="error", text=text[:_MAX_ERROR_CHARS], category=category)
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        data = None
    pending = _parse_pending(data)
    if pending is not None:
        return ToolResult(kind="pending", text=text, pending=pending)
    body, truncated = truncate_text(text, max_bytes)
    return ToolResult(kind="ok", text=body, truncated=truncated)


def _leaves(exc: BaseException) -> Iterator[BaseException]:
    """Flatten (possibly nested) exception groups into their leaf exceptions."""
    subs = getattr(exc, "exceptions", None)
    if subs:
        for sub in subs:
            yield from _leaves(sub)
    else:
        yield exc


_TRANSPORT_ERRORS = (
    httpx2.TransportError,
    anyio.ClosedResourceError,
    anyio.BrokenResourceError,
    anyio.EndOfStream,
    ConnectionError,
)


def _is_connection_loss(leaf: BaseException) -> bool:
    """True if ``leaf`` means the connection died, as opposed to a tool-level error."""
    if isinstance(leaf, MCPError):
        # The SDK reports a dead connection as an MCPError with a dedicated code.
        return leaf.error.code == CONNECTION_CLOSED and "not authorized" not in leaf.error.message
    return isinstance(leaf, _TRANSPORT_ERRORS)


class McpGatewaySession:
    """A live MCP session to the gateway, authenticated with a bearer token.

    The connection lives inside one dedicated task, because the MCP transport
    uses cancel scopes that must be entered and exited by the same task.

    If a call fails because the connection dropped, the session is discarded
    and re-established lazily on the next call, so a gateway restart does not
    end the conversation.
    """

    def __init__(
        self,
        url: str,
        token: str,
        *,
        max_result_bytes: int = 16_000,
        request_timeout: float = 60.0,
    ) -> None:
        self._url = url
        self._token = token
        self._max_result_bytes = max_result_bytes
        self._request_timeout = request_timeout
        self._session: ClientSession | None = None
        self._runner: asyncio.Task[None] | None = None
        self._stop: asyncio.Event | None = None

    async def connect(self) -> None:
        loop = asyncio.get_running_loop()
        ready: asyncio.Future[None] = loop.create_future()
        stop = asyncio.Event()

        async def run() -> None:
            try:
                async with (
                    httpx2.AsyncClient(
                        headers={"Authorization": f"Bearer {self._token}"},
                        timeout=self._request_timeout,
                    ) as client,
                    streamable_http_client(self._url, http_client=client) as streams,
                    ClientSession(streams[0], streams[1]) as session,
                ):
                    await session.initialize()
                    self._session = session
                    ready.set_result(None)
                    await stop.wait()
            except BaseException as exc:
                if not ready.done():
                    ready.set_exception(
                        exc if isinstance(exc, Exception) else RuntimeError("connection cancelled")
                    )
                else:
                    log.debug("gateway connection ended: %s", type(exc).__name__)
            finally:
                self._session = None

        self._stop = stop
        self._runner = asyncio.create_task(run(), name="sutra-gateway-session")
        try:
            await ready
        except Exception as exc:
            await self._drop()
            raise self._startup_error(exc) from exc

    def _startup_error(self, exc: BaseException) -> Exception:
        leaves = list(_leaves(exc))
        if any(isinstance(leaf, MCPError) for leaf in leaves):
            return GatewayAuthError(
                f"the gateway at {self._url} rejected the connection "
                "(check that SUTRA_TOKEN matches your token in gateway/tokens.yaml)"
            )
        return GatewayUnreachableError(
            f"could not reach the gateway at {self._url} (is it running?)"
        )

    async def _ensure(self) -> ClientSession:
        if self._session is None:
            log.info("reconnecting to the gateway")
            await self.connect()
        assert self._session is not None
        return self._session

    async def _drop(self) -> None:
        runner, stop = self._runner, self._stop
        self._runner = self._stop = self._session = None
        if stop is not None:
            stop.set()
        if runner is not None:
            with suppress(BaseException):
                await asyncio.wait_for(runner, timeout=5)

    async def list_tools(self) -> list[ToolDef]:
        session = await self._ensure()
        result = await session.list_tools()
        return [
            ToolDef(
                name=t.name,
                description=t.description or "",
                input_schema=t.input_schema or {"type": "object", "properties": {}},
            )
            for t in result.tools
        ]

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        try:
            session = await self._ensure()
            result = await session.call_tool(
                name, arguments, read_timeout_seconds=self._request_timeout
            )
        except (GatewayAuthError, GatewayUnreachableError) as exc:
            return ToolResult(kind="error", text=str(exc), category="disconnected")
        except Exception as exc:
            return await self._call_failure(exc)
        text = "".join(getattr(block, "text", "") for block in getattr(result, "content", []))
        return parse_tool_result(
            text, bool(getattr(result, "is_error", False)), self._max_result_bytes
        )

    async def _call_failure(self, exc: Exception) -> ToolResult:
        leaves = list(_leaves(exc))
        # A dead connection first, so it is not mistaken for a tool-level error.
        if any(_is_connection_loss(leaf) for leaf in leaves):
            await self._drop()
            return ToolResult(
                kind="error",
                text="the connection to the gateway was lost",
                category="disconnected",
            )
        for leaf in leaves:
            if isinstance(leaf, MCPError):
                message = leaf.error.message
                category = "unauthorized" if "not authorized" in message else "other"
                return ToolResult(kind="error", text=message[:_MAX_ERROR_CHARS], category=category)
        return ToolResult(kind="error", text=type(leaves[0]).__name__, category="other")

    async def close(self) -> None:
        await self._drop()
