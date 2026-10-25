"""Model access: the conversational model and the intent classifier model.

Both are small protocols so the turn loop can be tested with scripted fakes.
Messages use the Anthropic Messages format throughout.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

import anthropic


@dataclass
class ModelResponse:
    # Assistant content blocks in Messages format:
    # {"type": "text", "text": ...} or {"type": "tool_use", "id", "name", "input"}.
    content: list[dict[str, Any]]
    stop_reason: str | None = None

    @property
    def text(self) -> str:
        return "".join(b["text"] for b in self.content if b.get("type") == "text").strip()

    @property
    def tool_uses(self) -> list[dict[str, Any]]:
        return [b for b in self.content if b.get("type") == "tool_use"]


class ModelClient(Protocol):
    async def complete(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        allow_tools: bool = True,
    ) -> ModelResponse: ...


class IntentModel(Protocol):
    async def classify(self, *, system: str, user: str) -> str: ...


class ExtractorModel(Protocol):
    async def extract(self, *, system: str, user: str) -> list[dict[str, Any]]: ...


_CLASSIFY_TOOL = {
    "name": "classify",
    "description": "Record the label for the user's reply.",
    "input_schema": {
        "type": "object",
        "properties": {"label": {"type": "string", "enum": ["affirm", "deny", "modify", "unclear"]}},
        "required": ["label"],
    },
}


_EXTRACT_TOOL = {
    "name": "record_statements",
    "description": "Record the durable statements found in the user's message, possibly none.",
    "input_schema": {
        "type": "object",
        "properties": {
            "statements": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "content": {"type": "string"},
                        "spoken": {"type": "string"},
                        "kind": {
                            "type": "string",
                            "enum": ["fact", "preference", "routine", "correction"],
                        },
                    },
                    "required": ["content", "spoken", "kind"],
                },
            }
        },
        "required": ["statements"],
    },
}


class AnthropicModel:
    """Implements the conversation, intent, and extractor protocols over the Anthropic API."""

    def __init__(
        self,
        api_key: str,
        model: str,
        classifier_model: str,
        *,
        extractor_model: str | None = None,
        max_tokens: int = 1024,
    ) -> None:
        self._client = anthropic.AsyncAnthropic(api_key=api_key)
        self._model = model
        self._classifier_model = classifier_model
        self._extractor_model = extractor_model or classifier_model
        self._max_tokens = max_tokens

    async def complete(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        allow_tools: bool = True,
    ) -> ModelResponse:
        kwargs: dict[str, Any] = {
            "model": self._model,
            "max_tokens": self._max_tokens,
            "system": system,
            "messages": messages,
        }
        if tools:
            # The API requires tool definitions whenever the history contains
            # tool blocks, so a no-tools call keeps them but forbids use.
            kwargs["tools"] = tools
            if not allow_tools:
                kwargs["tool_choice"] = {"type": "none"}
        response = await self._client.messages.create(**kwargs)
        blocks: list[dict[str, Any]] = []
        for block in response.content:
            if block.type == "text":
                blocks.append({"type": "text", "text": block.text})
            elif block.type == "tool_use":
                blocks.append(
                    {"type": "tool_use", "id": block.id, "name": block.name, "input": block.input}
                )
        return ModelResponse(content=blocks, stop_reason=response.stop_reason)

    async def classify(self, *, system: str, user: str) -> str:
        response = await self._client.messages.create(
            model=self._classifier_model,
            max_tokens=64,
            system=system,
            messages=[{"role": "user", "content": user}],
            tools=[_CLASSIFY_TOOL],
            tool_choice={"type": "tool", "name": "classify"},
        )
        for block in response.content:
            if block.type == "tool_use" and block.name == "classify":
                label = block.input.get("label") if isinstance(block.input, dict) else None
                return label if isinstance(label, str) else ""
        return ""

    async def extract(self, *, system: str, user: str) -> list[dict[str, Any]]:
        response = await self._client.messages.create(
            model=self._extractor_model,
            max_tokens=512,
            system=system,
            messages=[{"role": "user", "content": user}],
            tools=[_EXTRACT_TOOL],
            tool_choice={"type": "tool", "name": "record_statements"},
        )
        for block in response.content:
            if block.type == "tool_use" and block.name == "record_statements":
                statements = block.input.get("statements") if isinstance(block.input, dict) else None
                return statements if isinstance(statements, list) else []
        return []
