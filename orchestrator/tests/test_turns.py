"""Turn loop: tools, history, errors, limits (tasks 7.2, 7.3, 7.9-7.12)."""

from __future__ import annotations

from sutra_orchestrator.gateway import ToolResult, truncate_text, parse_tool_result
from sutra_orchestrator.orchestrator import LIMIT_REPLY

from .fakes import (
    FakeGateway,
    FakeModel,
    assert_valid_history,
    default_tools,
    make_orchestrator,
    ok,
    resp,
    text,
    tool_use,
)


async def test_read_only_request_calls_tool_and_returns_reply():
    model = FakeModel(
        [
            resp(tool_use("finanxe_list_debts")),
            resp(text("You have three debts, about twelve thousand dollars in total.")),
        ]
    )
    gateway = FakeGateway(
        tools=default_tools(), results={"finanxe_list_debts": ok({"debts": [1, 2, 3]})}
    )
    orch, gateway = await make_orchestrator(model, gateway)

    reply = await orch.respond("how much debt do I have?")

    assert reply == "You have three debts, about twelve thousand dollars in total."
    assert gateway.calls == [("finanxe_list_debts", {})]
    # The tool result was fed back to the model.
    second = model.calls[1]["messages"][-1]["content"][0]
    assert second["type"] == "tool_result" and "debts" in second["content"]
    assert model.classify_calls == []  # no confirmation machinery involved
    assert orch.pending is None


async def test_turn_needing_two_tools_calls_both_and_returns_one_reply():
    model = FakeModel(
        [
            resp(
                tool_use("finanxe_list_debts", id="a"),
                tool_use("finanxe_get_snapshot", id="b"),
            ),
            resp(text("Here is the picture.")),
        ]
    )
    gateway = FakeGateway(
        tools=default_tools(),
        results={"finanxe_list_debts": ok({"d": 1}), "finanxe_get_snapshot": ok({"s": 1})},
    )
    orch, gateway = await make_orchestrator(model, gateway)

    reply = await orch.respond("give me an overview")

    assert reply == "Here is the picture."
    assert [n for n, _ in gateway.calls] == ["finanxe_list_debts", "finanxe_get_snapshot"]
    assert len(model.calls) == 2
    assert_valid_history(orch)


async def test_request_no_tool_can_serve_makes_no_tool_call():
    model = FakeModel([resp(text("Sorry, I can't book flights."))])
    orch, gateway = await make_orchestrator(model)
    assert await orch.respond("book me a flight") == "Sorry, I can't book flights."
    assert gateway.calls == []


async def test_followup_uses_session_history():
    model = FakeModel([resp(text("First answer.")), resp(text("Second answer."))])
    orch, _ = await make_orchestrator(model)
    await orch.respond("what is my biggest debt?")
    await orch.respond("and the second biggest?")
    roles_and_text = [
        (m["role"], m["content"][0].get("text")) for m in model.calls[1]["messages"]
    ]
    assert roles_and_text[0] == ("user", "what is my biggest debt?")
    assert roles_and_text[1] == ("assistant", "First answer.")
    assert roles_and_text[2] == ("user", "and the second biggest?")


async def test_gateway_confirm_is_not_offered_to_the_model():
    model = FakeModel([resp(text("hi"))])
    orch, _ = await make_orchestrator(model)  # the gateway lists gateway_confirm
    await orch.respond("hello")
    offered = {t["name"] for t in model.calls[0]["tools"]}
    assert "gateway_confirm" not in offered
    assert "finanxe_list_debts" in offered


async def test_unauthorized_error_gets_a_reply_and_session_survives():
    model = FakeModel(
        [
            resp(tool_use("finanxe_create_goal")),
            resp(text("You're not permitted to do that.")),
            resp(text("Sure, asking something else.")),
        ]
    )
    gateway = FakeGateway(
        tools=default_tools(),
        results={
            "finanxe_create_goal": ToolResult(
                kind="error", text='user "sid" is not authorized', category="unauthorized"
            )
        },
    )
    orch, gateway = await make_orchestrator(model, gateway)

    assert await orch.respond("make a goal") == "You're not permitted to do that."
    fed_back = model.calls[1]["messages"][-1]["content"][0]
    assert fed_back["is_error"] and "not permitted" in fed_back["content"]
    # Session still usable.
    assert await orch.respond("ok something else") == "Sure, asking something else."
    assert_valid_history(orch)


async def test_backend_unavailable_error_gets_a_reply():
    model = FakeModel(
        [resp(tool_use("finanxe_list_debts")), resp(text("Your finance service is down right now."))]
    )
    gateway = FakeGateway(
        tools=default_tools(),
        results={
            "finanxe_list_debts": ToolResult(
                kind="error", text="dial tcp 127.0.0.1:8002: connection refused", category="other"
            )
        },
    )
    orch, _ = await make_orchestrator(model, gateway)
    reply = await orch.respond("my debts?")
    assert reply == "Your finance service is down right now."


async def test_disconnected_error_is_reported_to_the_model_as_lost_connection():
    model = FakeModel([resp(tool_use("finanxe_list_debts")), resp(text("I lost the connection."))])
    gateway = FakeGateway(
        tools=default_tools(),
        results={
            "finanxe_list_debts": ToolResult(kind="error", text="lost", category="disconnected")
        },
    )
    orch, _ = await make_orchestrator(model, gateway)
    await orch.respond("debts?")
    fed_back = model.calls[1]["messages"][-1]["content"][0]["content"]
    assert "connection to the gateway was lost" in fed_back


async def test_tool_call_limit_stops_a_model_that_never_returns_text():
    # A model that asks for a tool on every call.
    forever = [resp(tool_use("finanxe_list_debts", id=f"t{i}")) for i in range(10)]
    model = FakeModel(forever)
    gateway = FakeGateway(tools=default_tools(), results={"finanxe_list_debts": ok({"d": 1})})
    orch, gateway = await make_orchestrator(model, gateway, max_tool_calls=3)

    reply = await orch.respond("loop forever")

    assert reply == LIMIT_REPLY
    assert len(gateway.calls) == 3
    assert_valid_history(orch)
    # The session is still usable after hitting the limit.
    model.script = [resp(text("fine"))]
    assert await orch.respond("next question") == "fine"
    assert_valid_history(orch)


async def test_model_requesting_several_tools_past_the_limit_skips_the_rest():
    model = FakeModel(
        [resp(*[tool_use("finanxe_list_debts", id=f"t{i}") for i in range(4)])]
    )
    gateway = FakeGateway(tools=default_tools(), results={"finanxe_list_debts": ok({"d": 1})})
    orch, gateway = await make_orchestrator(model, gateway, max_tool_calls=2)
    assert await orch.respond("many") == LIMIT_REPLY
    assert len(gateway.calls) == 2
    assert_valid_history(orch)


async def test_history_is_trimmed_to_the_turn_limit():
    model = FakeModel([resp(text(f"answer {i}")) for i in range(6)])
    orch, _ = await make_orchestrator(model, history_turns=3)
    for i in range(6):
        await orch.respond(f"question {i}")
    assert len(orch._history) == 3
    assert orch._history[0][0]["content"][0]["text"] == "question 3"
    assert_valid_history(orch)


async def test_empty_model_reply_falls_back_without_corrupting_history():
    model = FakeModel([resp(), resp(text("ok"))])
    orch, _ = await make_orchestrator(model)
    reply = await orch.respond("hello?")
    assert reply  # a fallback, not empty
    assert await orch.respond("again") == "ok"
    assert_valid_history(orch)


def test_oversized_results_are_truncated_with_a_marker():
    big = "x" * 5000
    body, truncated = truncate_text(big, 1000)
    assert truncated
    assert body.startswith("x" * 1000)
    assert "[truncated: result was 5000 bytes" in body

    result = parse_tool_result(big, False, 1000)
    assert result.kind == "ok" and result.truncated and "[truncated" in result.text


def test_small_results_are_not_truncated():
    result = parse_tool_result('{"a": 1}', False, 1000)
    assert result.kind == "ok" and not result.truncated and result.text == '{"a": 1}'


def test_truncation_never_splits_a_multibyte_character():
    body, truncated = truncate_text("é" * 100, 51)  # 51 is mid-character
    assert truncated
    body.encode("utf-8")  # must be valid


def test_parse_tool_result_detects_pending_only_with_all_three_fields():
    full = '{"pending_id": "p9", "description": "do it", "expires_at": "2026-10-12T12:05:00Z"}'
    result = parse_tool_result(full, False, 1000)
    assert result.kind == "pending"
    assert result.pending.pending_id == "p9" and result.pending.description == "do it"
    assert result.pending.expires_at.tzinfo is not None

    # A read-only payload that merely mentions pending_id is not a confirmation.
    partial = '{"pending_id": "p9", "description": "do it"}'
    assert parse_tool_result(partial, False, 1000).kind == "ok"
    assert parse_tool_result("not json", False, 1000).kind == "ok"


def test_parse_tool_result_classifies_errors():
    unauthorized = parse_tool_result('user "sid" is not authorized to call tool "x"', True, 1000)
    assert unauthorized.kind == "error" and unauthorized.category == "unauthorized"
    other = parse_tool_result("boom", True, 1000)
    assert other.kind == "error" and other.category == "other"
    long = parse_tool_result("e" * 5000, True, 1000)
    assert len(long.text) <= 400
