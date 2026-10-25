"""The Anthropic wrapper, against a mocked HTTP transport (no network, no key)."""

from __future__ import annotations

import json

import anthropic
import httpx2 as httpx

from sutra_orchestrator.model import AnthropicModel


def make_model(handler) -> tuple[AnthropicModel, list[dict]]:
    sent: list[dict] = []

    def wrapped(request: httpx.Request) -> httpx.Response:
        sent.append(json.loads(request.content))
        return handler(request)

    model = AnthropicModel("sk-test", "claude-sonnet-5-5", "claude-haiku-5-5")
    model._client = anthropic.AsyncAnthropic(
        api_key="sk-test", http_client=httpx.AsyncClient(transport=httpx.MockTransport(wrapped))
    )
    return model, sent


def message(content: list[dict], stop_reason: str = "end_turn") -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "id": "msg_1",
            "type": "message",
            "role": "assistant",
            "model": "claude-sonnet-5-5",
            "content": content,
            "stop_reason": stop_reason,
            "stop_sequence": None,
            "usage": {"input_tokens": 1, "output_tokens": 1},
        },
    )


TOOLS = [{"name": "list_debts", "description": "d", "input_schema": {"type": "object", "properties": {}}}]


async def test_complete_sends_system_messages_and_tools_and_parses_text_and_tool_use():
    model, sent = make_model(
        lambda r: message(
            [
                {"type": "text", "text": "Checking."},
                {"type": "tool_use", "id": "toolu_1", "name": "list_debts", "input": {}},
            ],
            "tool_use",
        )
    )
    response = await model.complete(
        system="be brief",
        messages=[{"role": "user", "content": [{"type": "text", "text": "hi"}]}],
        tools=TOOLS,
    )

    body = sent[0]
    assert body["model"] == "claude-sonnet-5-5" and body["system"] == "be brief"
    assert body["tools"] == TOOLS and "tool_choice" not in body
    assert response.text == "Checking."
    assert response.tool_uses == [{"type": "tool_use", "id": "toolu_1", "name": "list_debts", "input": {}}]


async def test_no_tools_call_with_tool_history_keeps_the_definitions_but_forbids_use():
    model, sent = make_model(lambda r: message([{"type": "text", "text": "Done."}]))
    history = [
        {"role": "user", "content": [{"type": "text", "text": "debts?"}]},
        {"role": "assistant", "content": [{"type": "tool_use", "id": "t1", "name": "list_debts", "input": {}}]},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t1", "content": "{}", "is_error": False}]},
    ]
    await model.complete(system="s", messages=history, tools=TOOLS, allow_tools=False)

    assert sent[0]["tools"] == TOOLS
    assert sent[0]["tool_choice"] == {"type": "none"}


async def test_call_without_any_tools_omits_the_tools_field():
    model, sent = make_model(lambda r: message([{"type": "text", "text": "hi"}]))
    await model.complete(system="s", messages=[{"role": "user", "content": "x"}], tools=[])
    assert "tools" not in sent[0] and "tool_choice" not in sent[0]


async def test_classify_forces_the_classify_tool_and_uses_the_classifier_model():
    model, sent = make_model(
        lambda r: message(
            [{"type": "tool_use", "id": "toolu_2", "name": "classify", "input": {"label": "affirm"}}],
            "tool_use",
        )
    )
    label = await model.classify(system="classifier prompt", user="reply: sure")

    body = sent[0]
    assert label == "affirm"
    assert body["model"] == "claude-haiku-5-5"
    assert body["tool_choice"] == {"type": "tool", "name": "classify"}
    assert body["tools"][0]["input_schema"]["properties"]["label"]["enum"] == [
        "affirm", "deny", "modify", "unclear",
    ]
    assert body["messages"] == [{"role": "user", "content": "reply: sure"}]


async def test_classify_without_a_tool_block_returns_empty_so_the_caller_treats_it_as_unclear():
    model, _ = make_model(lambda r: message([{"type": "text", "text": "affirm"}]))
    assert await model.classify(system="s", user="u") == ""
