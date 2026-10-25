"""Real MCP transport: a live server on localhost (tasks 2.1, 2.2, 2.4-2.6, 7.13)."""

from __future__ import annotations

import json
import socket
import threading
import time

import pytest
import uvicorn
from mcp.server.mcpserver import MCPServer
from mcp.shared.exceptions import MCPError

from sutra_orchestrator.classifier import IntentClassifier
from sutra_orchestrator.errors import GatewayAuthError, GatewayUnreachableError
from sutra_orchestrator.gateway import McpGatewaySession
from sutra_orchestrator.orchestrator import Orchestrator

from .fakes import FakeModel, resp, text, tool_use

TOKEN = "test-token-123"


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def build_app():
    server = MCPServer("fake-gateway")

    @server.tool()
    def list_debts() -> str:
        """List debts."""
        return json.dumps({"debts": [{"name": "Visa", "balance": 4000}]})

    @server.tool()
    def make_goal(name: str) -> str:
        """Create a goal (held for confirmation)."""
        return json.dumps(
            {
                "pending_id": "pend-1",
                "description": f"Create a goal named {name}.",
                "expires_at": "2099-01-01T00:00:00Z",
            }
        )

    @server.tool()
    def gateway_confirm(pending_id: str) -> str:
        """Confirm a pending call."""
        return json.dumps({"created": True, "pending_id": pending_id})

    @server.tool()
    def forbidden() -> str:
        """Always refused."""
        # The real gateway refuses with a JSON-RPC error carrying this text.
        raise MCPError(-32603, 'gateway: user "sid" is not authorized to call tool "forbidden"')

    @server.tool()
    def big() -> str:
        """Returns a large payload."""
        return "y" * 50_000

    inner = server.streamable_http_app()

    async def app(scope, receive, send):
        if scope["type"] == "http":
            headers = dict(scope["headers"])
            if headers.get(b"authorization") != f"Bearer {TOKEN}".encode():
                await send({"type": "http.response.start", "status": 401, "headers": []})
                await send({"type": "http.response.body", "body": b"unauthorized"})
                return
        await inner(scope, receive, send)

    return app


class LiveServer:
    def __init__(self, port: int):
        self.port = port
        self.url = f"http://127.0.0.1:{port}/mcp"
        self._server: uvicorn.Server | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        config = uvicorn.Config(build_app(), host="127.0.0.1", port=self.port, log_level="error", timeout_graceful_shutdown=1)
        self._server = uvicorn.Server(config)
        self._thread = threading.Thread(target=self._server.run, daemon=True)
        self._thread.start()
        deadline = time.time() + 10
        while not self._server.started:
            if time.time() > deadline:
                raise RuntimeError("test server did not start")
            time.sleep(0.02)

    def stop(self) -> None:
        if self._server is not None:
            self._server.should_exit = True
            self._thread.join(timeout=10)
            self._server = self._thread = None


@pytest.fixture
def live():
    server = LiveServer(free_port())
    server.start()
    yield server
    server.stop()


async def test_connect_list_and_call(live):
    session = McpGatewaySession(live.url, TOKEN)
    await session.connect()
    try:
        tools = {t.name: t for t in await session.list_tools()}
        assert {"list_debts", "make_goal", "gateway_confirm"} <= set(tools)
        assert tools["list_debts"].description == "List debts."
        assert tools["make_goal"].input_schema["type"] == "object"

        result = await session.call_tool("list_debts", {})
        assert result.kind == "ok" and json.loads(result.text)["debts"][0]["name"] == "Visa"
    finally:
        await session.close()


async def test_pending_results_are_recognised_over_the_real_transport(live):
    session = McpGatewaySession(live.url, TOKEN)
    await session.connect()
    try:
        result = await session.call_tool("make_goal", {"name": "Vacation"})
        assert result.kind == "pending"
        assert result.pending.pending_id == "pend-1"
        assert result.pending.description == "Create a goal named Vacation."
        assert result.pending.expires_at.year == 2099
    finally:
        await session.close()


async def test_tool_errors_are_returned_not_raised(live):
    session = McpGatewaySession(live.url, TOKEN)
    await session.connect()
    try:
        result = await session.call_tool("forbidden", {})
        assert result.kind == "error" and result.category == "unauthorized"
        unknown = await session.call_tool("no_such_tool", {})
        assert unknown.kind == "error"
        # Still usable afterwards.
        assert (await session.call_tool("list_debts", {})).kind == "ok"
    finally:
        await session.close()


async def test_oversized_results_are_truncated_end_to_end(live):
    session = McpGatewaySession(live.url, TOKEN, max_result_bytes=1000)
    await session.connect()
    try:
        result = await session.call_tool("big", {})
        assert result.kind == "ok" and result.truncated
        assert len(result.text.encode()) < 1200 and "[truncated" in result.text
    finally:
        await session.close()


# --- 7.13: startup failures --------------------------------------------------------------------


async def test_invalid_token_fails_at_startup_with_an_auth_error(live):
    session = McpGatewaySession(live.url, "wrong-token")
    with pytest.raises(GatewayAuthError, match="SUTRA_TOKEN"):
        await session.connect()


async def test_unreachable_gateway_fails_at_startup_naming_the_address():
    url = f"http://127.0.0.1:{free_port()}/mcp"
    session = McpGatewaySession(url, TOKEN)
    with pytest.raises(GatewayUnreachableError) as err:
        await session.connect()
    assert url in str(err.value)


# --- 2.6: reconnect --------------------------------------------------------------------------------


async def test_reconnects_on_the_next_call_after_the_gateway_restarts():
    server = LiveServer(free_port())
    server.start()
    session = McpGatewaySession(server.url, TOKEN, request_timeout=5)
    await session.connect()
    try:
        assert (await session.call_tool("list_debts", {})).kind == "ok"

        server.stop()
        down = await session.call_tool("list_debts", {})
        assert down.kind == "error" and down.category == "disconnected"

        server2 = LiveServer(server.port)
        server2.start()
        try:
            again = await session.call_tool("list_debts", {})  # reconnects lazily
            assert again.kind == "ok"
        finally:
            server2.stop()
    finally:
        await session.close()


# --- the orchestrator on the real transport --------------------------------------------------------


async def test_orchestrator_end_to_end_over_the_real_transport(live):
    session = McpGatewaySession(live.url, TOKEN)
    await session.connect()
    try:
        model = FakeModel(
            [
                resp(tool_use("list_debts")),
                resp(text("You owe about four thousand on your Visa.")),
                resp(tool_use("make_goal", {"name": "Vacation"})),
                resp(text("Create a Vacation goal. Yes or no?")),
                resp(text("Done, the goal is set up.")),
            ]
        )
        orch = Orchestrator(
            model=model, gateway=session, classifier=IntentClassifier(model), max_tool_calls=4
        )
        count = await orch.start()
        assert count == 4 and "gateway_confirm" not in orch.tool_names()  # 5 on the server, minus gateway_confirm

        assert "Visa" in await orch.respond("what do I owe?")
        assert "Yes or no" in await orch.respond("make a vacation goal")
        assert orch.pending.pending_id == "pend-1"
        assert await orch.respond("yes") == "Done, the goal is set up."
        assert orch.pending is None
    finally:
        await session.close()
