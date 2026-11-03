"""Speaker-bound confirmations: a pending action belongs to the person who
asked for it, not to the process.

These pin the gate that sits in front of the pending branch in
``Orchestrator.respond``: a turn that is not addressed to the assistant, or
that comes from any speaker other than the requesting one, never reaches
the consent classifier and never consumes the pending action.
"""

from __future__ import annotations

from .fakes import (
    FakeModel,
    assert_valid_history,
    make_orchestrator,
    pending,
    resp,
    text,
    tool_use,
)
from .test_confirmation import READBACK, gateway_with_pending, held_action_script

OWNER = "sidd"
OTHER = "guest"


async def hold_as_owner(model, gateway=None, speaker_id=OWNER):
    """Run the turn that gets an action held, as the given speaker."""
    orch, gateway = await make_orchestrator(model, gateway or gateway_with_pending())
    reply = await orch.respond("set up a vacation goal for two thousand", speaker_id=speaker_id)
    assert reply == READBACK
    assert orch.pending is not None and orch.pending.pending_id == "p1"
    return orch, gateway


# --- 1: the wrong speaker's "yes" confirms nothing ----------------------------------


async def test_wrong_speaker_yes_leaves_the_pending_action_untouched():
    model = FakeModel(
        held_action_script([resp(text("Sunny, actually.")), resp(text("Done."))]),
        labels={"sounds good": "affirm"},
    )
    orch, gateway = await hold_as_owner(model)
    assert orch.pending.requesting_speaker_id == OWNER

    # A different voice agreeing with something confirms nothing. The turn is
    # handled as an ordinary turn: the classifier is never even consulted.
    reply = await orch.respond("sounds good", speaker_id=OTHER)

    assert reply == "Sunny, actually."
    assert model.classify_calls == []
    assert gateway.calls_to("gateway_confirm") == []
    assert orch.pending is not None and orch.pending.pending_id == "p1"

    # And the action is still there for its owner to confirm.
    await orch.respond("yes", speaker_id=OWNER)
    assert gateway.calls_to("gateway_confirm") == [{"pending_id": "p1"}]
    assert orch.pending is None
    assert_valid_history(orch)


# --- 2: an unknown speaker's "yes" confirms nothing ---------------------------------


async def test_unknown_speaker_yes_leaves_the_pending_action_untouched():
    model = FakeModel(
        held_action_script([resp(text("Who is that?")), resp(text("Done."))]),
        labels={"sounds good": "affirm"},
    )
    orch, gateway = await hold_as_owner(model)

    # No recognised voiceprint (guest, TV): never affirmed.
    await orch.respond("sounds good", speaker_id=None)

    assert model.classify_calls == []
    assert gateway.calls_to("gateway_confirm") == []
    assert orch.pending is not None and orch.pending.pending_id == "p1"

    await orch.respond("yes", speaker_id=OWNER)
    assert gateway.calls_to("gateway_confirm") == [{"pending_id": "p1"}]
    assert_valid_history(orch)


# --- 3: a turn not addressed to the assistant is ignored entirely -------------------


async def test_not_addressed_turn_never_reaches_the_pending_branch():
    model = FakeModel(held_action_script(), labels={"sounds good": "affirm"})
    orch, gateway = await make_orchestrator(model, gateway_with_pending())

    # Not addressed, nothing pending: no model call, no reply, no history.
    assert await orch.respond("nice weather", addressed_to_assistant=False) == ""
    assert model.calls == []

    await orch.respond("set up a vacation goal for two thousand", speaker_id=OWNER)
    assert orch.pending is not None
    calls_before = len(model.calls)
    history_before = len(orch._flat_history())

    # "Yes, dinner at seven" said to someone else in the room, mid-session.
    reply = await orch.respond(
        "sounds good", speaker_id=OWNER, addressed_to_assistant=False
    )

    assert reply == ""
    assert len(model.calls) == calls_before  # the model never saw the turn
    assert model.classify_calls == []
    assert len(orch._flat_history()) == history_before  # nothing recorded
    assert gateway.calls_to("gateway_confirm") == []
    assert orch.pending is not None and orch.pending.pending_id == "p1"


# --- 4: the requesting speaker, addressed, still confirms the usual way -------------


async def test_requesting_speaker_addressed_yes_confirms_exactly_once():
    model = FakeModel(held_action_script([resp(text("Done, your Vacation goal is set up."))]))
    orch, gateway = await hold_as_owner(model)

    reply = await orch.respond("yes", speaker_id=OWNER)

    assert reply == "Done, your Vacation goal is set up."
    assert gateway.calls_to("gateway_confirm") == [{"pending_id": "p1"}]
    assert orch.pending is None
    assert_valid_history(orch)


# --- 5: closing the session drops the pending action ---------------------------------


async def test_session_close_drops_the_pending_action():
    model = FakeModel(held_action_script())
    orch, gateway = await hold_as_owner(model)

    orch.close_session()

    assert orch.pending is None
    assert orch._flat_history() == []

    # A later session is a new Orchestrator; its first "yes" is just a turn,
    # not a confirmation of the dropped action.
    model2 = FakeModel([resp(text("Yes to what?"))])
    orch2, gateway2 = await make_orchestrator(model2, gateway_with_pending())
    reply = await orch2.respond("yes", speaker_id=OWNER)

    assert reply == "Yes to what?"
    assert gateway2.calls_to("gateway_confirm") == []
    assert orch2.pending is None


# --- 6: classifier failure on a correctly bound turn stays fail-closed ---------------


async def test_classifier_failure_on_a_bound_turn_is_unclear_and_pending_survives():
    model = FakeModel(held_action_script())
    orch, gateway = await hold_as_owner(model)
    model.classify_error = RuntimeError("api down")

    reply = await orch.respond("sure thing", speaker_id=OWNER)

    assert gateway.calls_to("gateway_confirm") == []
    assert "yes or no" in reply.lower()  # re-asked, as before
    assert orch.pending is not None


# --- 7: the gate is the only path to the pending branch -------------------------------


async def test_gate_is_the_only_caller_that_sees_a_speaker_bound_turn():
    """By construction: grep the source, extending the gateway_confirm grep test."""
    import inspect

    from sutra_orchestrator import orchestrator

    source = inspect.getsource(orchestrator)

    # The addressee gate sits before the pending branch in the source.
    assert source.index("if not addressed_to_assistant") < source.index(
        "self._handle_pending("
    )
    # _handle_pending has exactly one call site, guarded by the
    # speaker-binding check on the line above it.
    lines = source.splitlines()
    call_idx = [i for i, line in enumerate(lines) if "self._handle_pending(" in line]
    assert len(call_idx) == 1 and "_speaker_may_confirm" in lines[call_idx[0] - 1]
    # gateway_confirm still has exactly one caller: the gate's confirm path.
    confirm_calls = [
        line.strip() for line in source.splitlines() if "call_tool(CONFIRM_TOOL" in line
    ]
    assert len(confirm_calls) == 1 and "_confirm_pending" in source


# --- guard: another speaker's turn cannot replace the held action ---------------------


async def test_other_speakers_turn_cannot_replace_the_pending_action():
    model = FakeModel(
        held_action_script(
            [
                resp(tool_use("finanxe_create_goal", {"name": "Boat"}, id="tu_9")),
                resp(text("One moment — something else is already waiting.")),
            ]
        )
    )
    gateway = gateway_with_pending()
    gateway.results["finanxe_create_goal"] = [
        pending("p1"),
        pending("p2", "Create a goal named Boat."),
    ]
    orch, gateway = await hold_as_owner(model, gateway)

    # The other speaker asks for their own held action mid-session. The
    # gateway holds it, but the orchestrator refuses to displace the
    # owner's pending action with it.
    await orch.respond("make a boat goal", speaker_id=OTHER)

    assert orch.pending is not None and orch.pending.pending_id == "p1"
    assert orch.pending.requesting_speaker_id == OWNER
    assert gateway.calls_to("gateway_confirm") == []
    refusal = model.calls[-1]["messages"][-1]["content"][0]
    assert refusal["is_error"] and "already awaiting" in refusal["content"]
