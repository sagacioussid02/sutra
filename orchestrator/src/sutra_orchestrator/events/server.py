"""A tiny loopback listener for envelopes the gateway forwards. Stdlib only, one route."""

from __future__ import annotations

import asyncio
import hmac
import json
import logging

from .kinds import EventError
from .service import EventsService

log = logging.getLogger(__name__)
MAX_BODY = 16 * 1024
_REASONS = {200: "OK", 202: "Accepted", 400: "Bad Request", 401: "Unauthorized", 404: "Not Found", 413: "Too Large", 503: "Unavailable"}


async def _reply(writer: asyncio.StreamWriter, code: int, body: dict[str, object] | None = None) -> None:
    data = json.dumps(body or {}).encode()
    writer.write(
        f"HTTP/1.1 {code} {_REASONS.get(code, 'Error')}\r\nContent-Type: application/json\r\n"
        f"Content-Length: {len(data)}\r\nConnection: close\r\n\r\n".encode() + data
    )
    await writer.drain()


class EventListener:
    def __init__(self, service: EventsService, port: int) -> None:
        self._service = service
        self._port = port
        self._server: asyncio.Server | None = None

    @property
    def port(self) -> int:
        if self._server and self._server.sockets:
            return self._server.sockets[0].getsockname()[1]
        return self._port

    async def start(self) -> None:
        self._server = await asyncio.start_server(self._handle, "127.0.0.1", self._port)

    async def stop(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            await asyncio.wait_for(self._serve(reader, writer), timeout=10)
        except Exception as exc:  # a bad client must never take the listener down
            log.debug("event listener request failed: %s", type(exc).__name__)
        finally:
            writer.close()

    async def _serve(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        request_line = (await reader.readline()).decode("latin-1").strip()
        headers: dict[str, str] = {}
        while True:
            line = (await reader.readline()).decode("latin-1").strip()
            if not line:
                break
            name, _, value = line.partition(":")
            headers[name.strip().lower()] = value.strip()
        if request_line.split(" ")[:2] != ["POST", "/events"]:
            return await _reply(writer, 404)
        if not self._service.secret or not hmac.compare_digest(
            headers.get("x-sutra-forward-secret", ""), self._service.secret
        ):
            return await _reply(writer, 401)
        length = int(headers.get("content-length", "0") or 0)
        if length <= 0 or length > MAX_BODY:
            return await _reply(writer, 413)
        try:
            data = json.loads(await reader.readexactly(length))
            stored = self._service.ingest(data)
        except (EventError, ValueError) as exc:
            return await _reply(writer, 400, {"error": str(exc)})
        await _reply(writer, 202 if stored else 200, {"stored": stored})
