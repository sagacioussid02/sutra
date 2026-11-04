"""Model access: the conversational model and the intent classifier model.

Both are small protocols so the turn loop can be tested with scripted fakes.
Messages use the Anthropic Messages format throughout.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

import anthropic

from .agents.types import StepResult


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
        on_text: Callable[[str], None] | None = None,
    ) -> ModelResponse: ...


class IntentModel(Protocol):
    async def classify(self, *, system: str, user: str) -> str: ...


class InterestModel(Protocol):
    async def reflect_interests(self, *, system: str, user: str) -> list[dict[str, Any]]: ...


class StructuredModel(Protocol):
    """A forced-schema call: the named schema's object back, or {} if the model gave nothing."""

    async def structured(self, *, name: str, system: str, user: str) -> dict[str, Any]: ...


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


_INTERESTS_TOOL = {
    "name": "record_interests",
    "description": "Record interest topics found in the user's utterances, possibly none.",
    "input_schema": {
        "type": "object",
        "properties": {
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "label": {"type": "string"},
                        "relation": {"type": "string", "enum": ["new", "strengthens", "changes"]},
                        "target": {"type": "integer"},
                        "before": {"type": "string"},
                        "now": {"type": "string"},
                        "evidence": {"type": "array", "items": {"type": "integer"}},
                    },
                    "required": ["label", "relation", "evidence"],
                },
            }
        },
        "required": ["items"],
    },
}


_STEPS = ["example", "deeper", "practice", "decision"]

# Forced-schema calls for the episode graph and the offer judge, keyed by name.
STRUCTURED_TOOLS: dict[str, dict[str, Any]] = {
    "episode": {
        "name": "record_episode",
        "description": "Summarise the conversation as one episode, or say it is not worth keeping.",
        "input_schema": {
            "type": "object",
            "properties": {
                "keep": {"type": "boolean"},
                "topic": {"type": "string"},
                "gist": {"type": "string"},
                "mode": {
                    "type": "string",
                    "enum": ["explained", "planned", "worked_on", "decided", "asked"],
                },
                "open": {"type": "array", "items": {"type": "string", "enum": _STEPS}},
                "entities": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["keep"],
        },
    },
    "links": {
        "name": "record_links",
        "description": "Record how the new episode relates to the numbered earlier ones, possibly none.",
        "input_schema": {
            "type": "object",
            "properties": {
                "edges": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "target": {"type": "integer"},
                            "type": {
                                "type": "string",
                                "enum": [
                                    "same_topic",
                                    "extends",
                                    "prerequisite_of",
                                    "applies_to",
                                    "updates",
                                ],
                            },
                            "strength": {"type": "number"},
                            "reason": {"type": "string"},
                        },
                        "required": ["target", "type", "strength", "reason"],
                    },
                }
            },
            "required": ["edges"],
        },
    },
    "advice": {
        "name": "record_advice",
        "description": "Name the one earlier episode worth following up now, or 0 for none.",
        "input_schema": {
            "type": "object",
            "properties": {
                "choice": {"type": "integer"},
                "benefit": {"type": "number"},
                "reason": {"type": "string"},
                "step": {"type": "string", "enum": [*_STEPS, "none"]},
            },
            "required": ["choice"],
        },
    },
    "idle_pick": {
        "name": "record_pick",
        "description": "Choose one topic worth researching now, or 0 for none.",
        "input_schema": {
            "type": "object",
            "properties": {
                "choice": {"type": "integer"},
                "brief": {"type": "string"},
                "kind": {"type": "string", "enum": ["whats_new", "upcoming", "compare", "how_to"]},
                "value": {"type": "number"},
                "revisit_after_days": {"type": "number"},
            },
            "required": ["choice"],
        },
    },
    "lesson_reflect": {
        "name": "record_lessons",
        "description": "Record lessons about how the assistant should behave, possibly none.",
        "input_schema": {
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "text": {"type": "string"},
                            "evidence": {"type": "array", "items": {"type": "integer"}},
                            "recurrence_of": {"type": "integer"},
                        },
                        "required": ["text", "evidence"],
                    },
                }
            },
            "required": ["items"],
        },
    },
    "humor_reaction": {
        "name": "record_humor",
        "description": "Record whether the assistant joked and how the person reacted.",
        "input_schema": {
            "type": "object",
            "properties": {
                "joked": {"type": "boolean"},
                "reaction": {"type": "string", "enum": ["laughed", "smiled", "neutral", "groaned", "annoyed"]},
                "stop": {"type": "boolean"},
            },
            "required": ["joked"],
        },
    },
    "life_extract": {
        "name": "record_life",
        "description": "Record the people and plans the person mentioned, possibly none.",
        "input_schema": {
            "type": "object",
            "properties": {
                "people": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {"name": {"type": "string"}, "relation": {"type": "string"}},
                        "required": ["name"],
                    },
                },
                "events": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "text": {"type": "string"},
                            "when": {"type": "string"},
                            "who": {"type": "string"},
                        },
                        "required": ["text"],
                    },
                },
            },
            "required": ["people", "events"],
        },
    },
    "auth_question": {
        "name": "record_auth_question",
        "description": "Record one check question, grounded in a numbered fact.",
        "input_schema": {
            "type": "object",
            "properties": {"fact": {"type": "integer"}, "question": {"type": "string"}, "answer": {"type": "string"}},
            "required": ["fact", "question", "answer"],
        },
    },
    "auth_judge": {
        "name": "record_auth_verdict",
        "description": "Record whether the answer is right.",
        "input_schema": {
            "type": "object",
            "properties": {"verdict": {"type": "string", "enum": ["match", "no_match", "unsure"]}},
            "required": ["verdict"],
        },
    },
    "judgement": {
        "name": "record_judgement",
        "description": "Decide whether to speak up now, and how.",
        "input_schema": {
            "type": "object",
            "properties": {
                "decision": {"type": "string", "enum": ["offer", "hold", "drop"]},
                "benefit": {"type": "number"},
                "style": {"type": "string", "enum": ["ask", "tell"]},
                "teaser": {"type": "string"},
                "retry_after_hours": {"type": "number"},
                "reason": {"type": "string"},
            },
            "required": ["decision", "benefit", "style", "teaser", "reason"],
        },
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
        agent_model: str | None = None,
        max_tokens: int = 1024,
    ) -> None:
        self._client = anthropic.AsyncAnthropic(api_key=api_key)
        self._model = model
        self._classifier_model = classifier_model
        self._extractor_model = extractor_model or classifier_model
        self._agent_model = agent_model or classifier_model
        self._max_tokens = max_tokens

    async def complete(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        allow_tools: bool = True,
        on_text: Callable[[str], None] | None = None,
    ) -> ModelResponse:
        """One model step. With ``on_text`` the reply is streamed and each text delta is passed to it."""
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
        if on_text is None:
            response = await self._client.messages.create(**kwargs)
        else:
            async with self._client.messages.stream(**kwargs) as stream:
                async for delta in stream.text_stream:
                    on_text(delta)
                response = await stream.get_final_message()
        blocks: list[dict[str, Any]] = []
        for block in response.content:
            if block.type == "text":
                blocks.append({"type": "text", "text": block.text})
            elif block.type == "tool_use":
                blocks.append(
                    {"type": "tool_use", "id": block.id, "name": block.name, "input": block.input}
                )
        return ModelResponse(content=blocks, stop_reason=response.stop_reason)

    async def research_step(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        max_searches: int,
        max_tokens: int,
    ) -> StepResult:
        """One request for a research run: the web search server tool plus any allowlisted tools."""
        all_tools = list(tools)
        if max_searches > 0:
            all_tools.append(
                {"type": "web_search_20250305", "name": "web_search", "max_uses": max_searches}
            )
        kwargs: dict[str, Any] = {
            "model": self._agent_model,
            "max_tokens": max(1, min(max_tokens, 4096)),
            "system": system,
            "messages": messages,
        }
        if all_tools:
            kwargs["tools"] = all_tools
        response = await self._client.messages.create(**kwargs)
        usage = getattr(response, "usage", None)
        server = getattr(usage, "server_tool_use", None)
        return StepResult(
            content=[b.model_dump(mode="json", exclude_none=True) for b in response.content],
            stop_reason=response.stop_reason,
            output_tokens=getattr(usage, "output_tokens", 0) or 0,
            searches=getattr(server, "web_search_requests", 0) or 0,
        )

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

    async def reflect_interests(self, *, system: str, user: str) -> list[dict[str, Any]]:
        response = await self._client.messages.create(
            model=self._extractor_model,
            max_tokens=700,
            system=system,
            messages=[{"role": "user", "content": user}],
            tools=[_INTERESTS_TOOL],
            tool_choice={"type": "tool", "name": "record_interests"},
        )
        for block in response.content:
            if block.type == "tool_use" and block.name == "record_interests":
                items = block.input.get("items") if isinstance(block.input, dict) else None
                return items if isinstance(items, list) else []
        return []

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

    async def structured(self, *, name: str, system: str, user: str) -> dict[str, Any]:
        tool = STRUCTURED_TOOLS[name]
        response = await self._client.messages.create(
            model=self._extractor_model,
            max_tokens=700,
            system=system,
            messages=[{"role": "user", "content": user}],
            tools=[tool],
            tool_choice={"type": "tool", "name": tool["name"]},
        )
        for block in response.content:
            if block.type == "tool_use" and block.name == tool["name"]:
                return block.input if isinstance(block.input, dict) else {}
        return {}
