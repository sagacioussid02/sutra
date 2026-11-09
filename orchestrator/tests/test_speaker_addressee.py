"""Speaker identification and addressee detection (OpenSpec speaker-addressee).

Covers the proposal's tasks: the speaker signal and its registry (1.1,
1.3), enrolment (2.1-2.3), the addressee pre-filter, classifier and turn
gate (3.1-3.4), confirmation binding on the real signal (4.1-4.3), and
the feature switch (5.1). The manual check with a real setup (5.3) and
the identification implementation's evaluation on the owner's voice
(1.2) are not automatable here; the shipped identifier is the null one,
which always returns unknown.
"""

from __future__ import annotations

import asyncio
import logging

import pytest

from sutra_orchestrator.config import ConfigError, load_config
from sutra_orchestrator.speaker import (
    Addressee,
    AddresseeClassifier,
    ConversationState,
    EnrolmentStore,
    NullIdentifier,
    SpeakerService,
    SpeakerSignal,
    TurnGate,
    prefilter,
)
from sutra_orchestrator.voice.loop import VoiceSession, VoiceSettings
from sutra_orchestrator.voice.types import Engines, Transcript

from .fakes import FakeModel, assert_valid_history, make_orchestrator, resp, text, tool_use
from .test_confirmation import READBACK, gateway_with_pending, held_action_script
from .test_voice import FakeRecorder, FakeSpeaker, FakeTranscriber

OWNER = "sidd"
OTHER = "guest"


def owner_signal(confidence: float = 0.9) -> SpeakerSignal:
    return SpeakerSignal.identified(OWNER, confidence, "enrolled-voiceprint")


def other_signal(confidence: float = 0.9) -> SpeakerSignal:
    return SpeakerSignal.identified(OTHER, confidence, "enrolled-voiceprint")


# --- 1: the signal ------------------------------------------------------------


def test_unknown_signal_carries_no_confidence_and_no_method():
    signal = SpeakerSignal.unknown()
    assert signal.speaker_id is None and signal.confidence == 0.0
    assert not signal.is_known and signal.method == "none"


def test_identified_signal_validates_its_confidence():
    assert SpeakerSignal.identified(OWNER, 0.9, "enrolled-voiceprint").is_known
    with pytest.raises(ValueError):
        SpeakerSignal.identified(OWNER, 1.5, "enrolled-voiceprint")
    with pytest.raises(ValueError):
        SpeakerSignal(speaker_id=None, confidence=0.5)
    with pytest.raises(ValueError):
        SpeakerSignal.identified("  ", 0.9, "enrolled-voiceprint")


def test_null_identifier_always_returns_unknown_without_a_network():
    identifier = NullIdentifier()
    assert identifier.identify(b"somebody speaking") == SpeakerSignal.unknown()
    assert identifier.identify(b"") == SpeakerSignal.unknown()


# --- 2: enrolment -------------------------------------------------------------


def test_enrolment_flow_lists_and_deletes(tmp_path):
    store = EnrolmentStore(tmp_path / "speakers")
    assert store.list_profiles() == []

    store.start_enrolment("sidd", "user-sidd")
    assert store.enrolment_in_progress == "sidd"
    store.add_sample(b"wav-one")
    store.add_sample(b"wav-two")
    profile = store.finish_enrolment()

    assert profile.label == "sidd" and profile.user_id == "user-sidd" and profile.samples == 2
    assert store.is_enrolled("sidd") and store.user_id_for("sidd") == "user-sidd"
    assert [p.label for p in store.list_profiles()] == ["sidd"]
    assert sorted((tmp_path / "speakers" / "samples" / "sidd").iterdir())

    # Deletion takes effect immediately: the next utterance is unknown.
    assert store.delete("sidd") is True
    assert not store.is_enrolled("sidd") and store.list_profiles() == []
    assert not (tmp_path / "speakers" / "samples" / "sidd").exists()
    assert store.delete("sidd") is False  # deleting twice is a no-op


def test_enrolment_needs_an_explicit_command(tmp_path):
    store = EnrolmentStore(tmp_path / "speakers")
    with pytest.raises(ValueError):
        store.add_sample(b"wav")
    with pytest.raises(ValueError):
        store.finish_enrolment()
    store.start_enrolment("sidd", "user-sidd")
    with pytest.raises(ValueError):
        store.finish_enrolment()  # no samples recorded yet
    store.cancel_enrolment()
    assert store.list_profiles() == []
    # Being overheard enrols nobody: identification never creates a profile.
    NullIdentifier().identify(b"overheard speech")
    assert store.list_profiles() == []


def test_enrolment_rejects_bad_labels_and_duplicates(tmp_path):
    store = EnrolmentStore(tmp_path / "speakers")
    for bad in ("", "  ", "../escape", "a/b"):
        with pytest.raises(ValueError):
            store.start_enrolment(bad, "user-x")
    store.start_enrolment("sidd", "user-sidd")
    store.add_sample(b"wav")
    store.finish_enrolment()
    with pytest.raises(ValueError):
        store.start_enrolment("sidd", "user-sidd")
    store.start_enrolment("guest", "user-guest")
    with pytest.raises(ValueError):
        store.start_enrolment("other", "user-other")  # one enrolment at a time


def test_enrolment_profiles_never_reach_model_prompts(tmp_path):
    model = FakeModel(labels={"pass the salt": "elsewhere"})
    classifier = AddresseeClassifier(model, ("sutra",))
    store = EnrolmentStore(tmp_path / "speakers")
    store.start_enrolment("sidd", "user-sidd")
    store.add_sample(b"wav")
    store.finish_enrolment()
    service = SpeakerService(
        classifier=classifier, enrolment=store, enabled=True, assistant_names=("sutra",)
    )
    service.note_conversation_opened()
    # The opening turn is addressed by construction; the next one goes to
    # the classifier, which is the call this test inspects.
    asyncio.run(service.classify_utterance("hello", SpeakerSignal.unknown()))
    asyncio.run(service.classify_utterance("pass the salt", SpeakerSignal.unknown()))
    assert model.classify_calls, "the classifier should have been consulted"
    # The only model input is the utterance plus untrusted-signal labels:
    # no enrolment label, user id, or sample ever appears in it.
    assert all("sidd" not in call["user"] for call in model.classify_calls)


# --- 3: addressee -------------------------------------------------------------


def test_prefilter_names_push_to_talk_and_just_opened():
    closed = ConversationState(open=False)
    assert prefilter("sutra, what time is it", closed, ("sutra",)) is Addressee.ADDRESSED
    assert prefilter("hey sutra", closed, ("hey sutra", "sutra")) is Addressee.ADDRESSED
    assert prefilter("what time is it", closed, ("sutra",)) is Addressee.ELSEWHERE
    assert prefilter("pass the salt", ConversationState(open=True), ("sutra",)) is None
    assert (
        prefilter("anything", ConversationState(open=True, push_to_talk=True), ("sutra",))
        is Addressee.ADDRESSED
    )
    assert (
        prefilter("anything", ConversationState(open=True, just_opened=True), ("sutra",))
        is Addressee.ADDRESSED
    )


async def test_classifier_uses_the_model_for_undecided_utterances():
    model = FakeModel(labels={"pass the salt": "elsewhere", "what time is it": "addressed"})
    classifier = AddresseeClassifier(model, ("sutra",))
    state = ConversationState(open=True, opened_by=OWNER)
    assert (
        await classifier.classify("pass the salt", owner_signal(), state) is Addressee.ELSEWHERE
    )
    assert (
        await classifier.classify("what time is it", owner_signal(), state)
        is Addressee.ADDRESSED
    )
    # No label for this one: the model says unclear, and so does the classifier.
    assert (
        await classifier.classify("hmm", owner_signal(), state) is Addressee.UNCLEAR
    )


async def test_classifier_failure_is_unclear_never_addressed():
    model = FakeModel(labels={"pass the salt": "elsewhere"})
    model.classify_error = RuntimeError("api down")
    classifier = AddresseeClassifier(model, ("sutra",))
    assert (
        await classifier.classify("pass the salt", owner_signal(), ConversationState(open=True))
        is Addressee.UNCLEAR
    )


async def test_classifier_without_a_model_is_unclear_off_the_fast_path():
    classifier = AddresseeClassifier(None, ("sutra",))
    assert (
        await classifier.classify("hmm", owner_signal(), ConversationState(open=True))
        is Addressee.UNCLEAR
    )
    assert (
        await classifier.classify("sutra, hello", owner_signal(), ConversationState(open=False))
        is Addressee.ADDRESSED
    )


def test_turn_gate_is_asymmetric():
    assert TurnGate.decide(Addressee.ADDRESSED) == "proceed"
    assert TurnGate.decide(Addressee.UNCLEAR) == "answer_only"
    assert TurnGate.decide(Addressee.ELSEWHERE) == "ignore"


# --- 4: confirmations consume the signal --------------------------------------


async def hold_as_owner(model, *, signal=None, speaker_enabled=True, gateway=None):
    """Run the turn that gets an action held, as the owner, on the real signal."""
    orch, gateway = await make_orchestrator(
        model, gateway or gateway_with_pending(), speaker_enabled=speaker_enabled
    )
    kwargs = {"signal": signal if signal is not None else owner_signal()}
    if not speaker_enabled:
        # With the switch off the signal is ignored, so the legacy
        # speaker_id binds the claim instead.
        kwargs["speaker_id"] = OWNER
    reply = await orch.respond("set up a vacation goal for two thousand", **kwargs)
    assert reply == READBACK
    assert orch.pending is not None and orch.pending.pending_id == "p1"
    return orch, gateway


async def test_bound_speaker_confirms_at_sufficient_confidence():
    model = FakeModel(held_action_script([resp(text("Done, your Vacation goal is set up."))]))
    orch, gateway = await hold_as_owner(model)
    reply = await orch.respond("yes", signal=owner_signal(0.9))
    assert reply == "Done, your Vacation goal is set up."
    assert gateway.calls_to("gateway_confirm") == [{"pending_id": "p1"}]
    assert orch.pending is None
    assert_valid_history(orch)


async def test_different_speaker_cannot_confirm_and_the_attempt_is_audited(caplog):
    model = FakeModel(
        held_action_script([resp(text("Sunny, actually.")), resp(text("Done."))]),
        labels={"sounds good": "affirm"},
    )
    orch, gateway = await hold_as_owner(model)
    with caplog.at_level(logging.INFO, logger="sutra_orchestrator"):
        reply = await orch.respond("yes", signal=other_signal(0.9))
    assert reply == "Sunny, actually."
    assert model.classify_calls == []
    assert gateway.calls_to("gateway_confirm") == []
    assert orch.pending is not None and orch.pending.pending_id == "p1"
    assert any("p1" in r.message and "guest" in r.message for r in caplog.records)
    await orch.respond("yes", signal=owner_signal(0.9))
    assert gateway.calls_to("gateway_confirm") == [{"pending_id": "p1"}]


async def test_unknown_speaker_cannot_confirm_an_identified_claim():
    model = FakeModel(held_action_script([resp(text("Who is that?")), resp(text("Done."))]))
    orch, gateway = await hold_as_owner(model)
    await orch.respond("yes", signal=SpeakerSignal.unknown())
    assert gateway.calls_to("gateway_confirm") == []
    assert orch.pending is not None
    await orch.respond("yes", signal=owner_signal(0.9))
    assert gateway.calls_to("gateway_confirm") == [{"pending_id": "p1"}]


async def test_low_confidence_cannot_confirm():
    model = FakeModel(held_action_script([resp(text("Hmm.")), resp(text("Done."))]))
    orch, gateway = await hold_as_owner(model)
    await orch.respond("yes", signal=owner_signal(0.3))
    assert gateway.calls_to("gateway_confirm") == []
    assert orch.pending is not None
    await orch.respond("yes", signal=owner_signal(0.7))  # exactly at the threshold
    assert gateway.calls_to("gateway_confirm") == [{"pending_id": "p1"}]


async def test_unidentified_claim_keeps_todays_voice_posture():
    """Voice before any identification implementation: both sides unknown.

    A claim requested by no identified speaker is still confirmable by an
    unknown voice, exactly as today — otherwise turning the feature on
    with the null identifier would make voice confirmations impossible.
    """
    model = FakeModel(held_action_script([resp(text("Done."))]))
    orch, gateway = await make_orchestrator(model, gateway_with_pending(), speaker_enabled=True)
    reply = await orch.respond(
        "set up a vacation goal for two thousand", signal=SpeakerSignal.unknown()
    )
    assert reply == READBACK and orch.pending.requesting_speaker_id is None
    await orch.respond("yes", signal=SpeakerSignal.unknown())
    assert gateway.calls_to("gateway_confirm") == [{"pending_id": "p1"}]


async def test_feature_off_is_byte_identical_to_today():
    model = FakeModel(held_action_script([resp(text("Done."))]))
    orch, gateway = await hold_as_owner(model, speaker_enabled=False)
    # With the switch off the signal is ignored: the legacy speaker_id rule
    # decides, and a verdict of elsewhere is ignored too.
    reply = await orch.respond(
        "yes", speaker_id=OWNER, signal=other_signal(0.9), addressee=Addressee.ELSEWHERE
    )
    assert gateway.calls_to("gateway_confirm") == [{"pending_id": "p1"}]
    assert orch.pending is None


# --- 3.4 / 5: the gate in the turn --------------------------------------------


async def test_elsewhere_turn_is_ignored_entirely():
    model = FakeModel([resp(text("should never be spoken"))])
    orch, _ = await make_orchestrator(model, speaker_enabled=True)
    history_before = len(orch._flat_history())
    assert await orch.respond("pass the salt", addressee=Addressee.ELSEWHERE) == ""
    assert model.calls == []
    assert len(orch._flat_history()) == history_before


async def test_unclear_turn_is_answered_without_tools_or_confirmation():
    model = FakeModel(
        held_action_script([resp(text("Done."))]),
        labels={"sounds good": "affirm"},
    )
    orch, gateway = await hold_as_owner(model)
    # "sounds good" on an unclear turn: answered, but the pending action is untouched.
    reply = await orch.respond("sounds good", signal=owner_signal(), addressee=Addressee.UNCLEAR)
    assert reply == "Done."
    assert model.calls[-1]["allow_tools"] is False
    assert gateway.calls_to("gateway_confirm") == []
    assert orch.pending is not None and orch.pending.pending_id == "p1"
    # And a direct question on an unclear turn is still answered normally.
    model2 = FakeModel([resp(text("It is three o'clock."))])
    orch2, _ = await make_orchestrator(model2, speaker_enabled=True)
    assert (
        await orch2.respond("what time is it", addressee=Addressee.UNCLEAR)
        == "It is three o'clock."
    )
    assert model2.calls[-1]["allow_tools"] is False


async def test_addressed_turn_proceeds_with_tools():
    model = FakeModel(held_action_script())
    orch, gateway = await make_orchestrator(model, gateway_with_pending(), speaker_enabled=True)
    reply = await orch.respond(
        "set up a vacation goal for two thousand",
        signal=owner_signal(),
        addressee=Addressee.ADDRESSED,
    )
    assert reply == READBACK
    assert model.calls[0]["allow_tools"] is True  # the turn offered tools, as usual
    assert orch.pending is not None


# --- 5.1: config --------------------------------------------------------------


def test_speaker_is_off_by_default_and_configurable():
    cfg = load_config(
        {"SUTRA_TOKEN": "t", "ANTHROPIC_API_KEY": "k"}, dotenv_path=None
    )
    assert cfg.speaker_enabled is False
    assert cfg.speaker_confirm_confidence == 0.7
    assert cfg.speaker_dir == "data"
    cfg = load_config(
        {
            "SUTRA_TOKEN": "t",
            "ANTHROPIC_API_KEY": "k",
            "SUTRA_SPEAKER": "on",
            "SUTRA_SPEAKER_CONFIRM_CONFIDENCE": "0.8",
            "SUTRA_SPEAKER_DIR": "speakers",
        },
        dotenv_path=None,
    )
    assert cfg.speaker_enabled and cfg.speaker_confirm_confidence == 0.8
    assert cfg.speaker_dir == "speakers"
    with pytest.raises(ConfigError):
        load_config(
            {"SUTRA_TOKEN": "t", "ANTHROPIC_API_KEY": "k", "SUTRA_SPEAKER_CONFIRM_CONFIDENCE": "1.5"},
            dotenv_path=None,
        )


# --- service ------------------------------------------------------------------


async def test_service_is_inert_when_disabled():
    model = FakeModel(labels={"pass the salt": "elsewhere"})
    service = SpeakerService(
        classifier=AddresseeClassifier(model, ("sutra",)), enabled=False
    )
    assert service.identify(b"wav") == SpeakerSignal.unknown()
    assert await service.classify_utterance("pass the salt", SpeakerSignal.unknown()) is None
    assert model.classify_calls == []


async def test_service_tracks_the_conversation_opening():
    model = FakeModel(labels={"pass the salt": "elsewhere"})
    service = SpeakerService(
        classifier=AddresseeClassifier(model, ("sutra",)),
        enabled=True,
        assistant_names=("sutra",),
    )
    service.note_conversation_opened(opened_by=OWNER)
    # The turn that opened it is addressed without a model call.
    assert (
        await service.classify_utterance("hmm", owner_signal(), push_to_talk=False)
        is Addressee.ADDRESSED
    )
    assert model.classify_calls == []
    # The next turn goes to the classifier.
    assert (
        await service.classify_utterance("pass the salt", owner_signal(), push_to_talk=False)
        is Addressee.ELSEWHERE
    )
    service.note_conversation_closed()
    assert (
        await service.classify_utterance("pass the salt", owner_signal(), push_to_talk=False)
        is Addressee.ELSEWHERE
    )


# --- voice loop -----------------------------------------------------------------


class RecordingOrchestrator:
    """A lane that records the turn context the loop passed it."""

    def __init__(self, replies, pending=None):
        self.replies = list(replies)
        self.pending = pending
        self.heard: list[tuple[str, dict]] = []

    async def respond(self, text, **kwargs):
        self.heard.append((text, kwargs))
        return self.replies.pop(0)

    def cancel_pending(self):
        self.pending = None

    async def flush(self):
        pass


class CapturingIdentifier:
    """An identifier that records the audio it was given, then says unknown."""

    def __init__(self):
        self.seen: list[bytes] = []

    def identify(self, wav: bytes) -> SpeakerSignal:
        self.seen.append(wav)
        return SpeakerSignal.unknown()


def _make_session(orch, clips, transcripts, *, service=None, activation="button"):
    speaker = FakeSpeaker()
    local = Engines(FakeTranscriber([]), FakeSpeaker(), "local")
    eng = Engines(FakeTranscriber(transcripts), speaker, "cloud")
    session = VoiceSession(
        orch,
        FakeRecorder(clips),
        eng,
        local,
        VoiceSettings(filler_delay=5.0, activation=activation),
        read=lambda prompt: asyncio.sleep(0, result=""),
        out=lambda line: None,
    )
    if service is not None:
        session.attach_speaker(service)
    return session, speaker


async def test_loop_attaches_the_signal_and_verdict_to_each_turn():
    identifier = CapturingIdentifier()
    service = SpeakerService(identifier=identifier, enabled=True, assistant_names=("sutra",))
    orch = RecordingOrchestrator(["Five projects."])
    session, speaker = _make_session(
        orch, [b"wav-bytes"], [Transcript("what projects", 0.9)], service=service
    )
    await session._turn()
    assert len(orch.heard) == 1
    text, kwargs = orch.heard[0]
    assert text == "what projects"
    assert kwargs["signal"] == SpeakerSignal.unknown()
    assert kwargs["addressee"] is Addressee.ADDRESSED  # push-to-talk counts as addressed
    assert identifier.seen == [b"wav-bytes"]  # the captured audio reached identification
    assert speaker.said == ["Five projects."]


async def test_loop_ignores_side_conversation_mid_session():
    model = FakeModel(labels={"pass the salt": "elsewhere"})
    service = SpeakerService(
        classifier=AddresseeClassifier(model, ("sutra",)),
        enabled=True,
        assistant_names=("sutra",),
    )
    orch = RecordingOrchestrator(["Sunny.", "ignored?"])
    session, speaker = _make_session(
        orch,
        [b"w", b"w"],
        [Transcript("sutra, what is the weather", 0.9), Transcript("pass the salt", 0.9)],
        service=service,
        activation="wake",
    )
    service.note_conversation_opened(opened_by=OWNER)
    await session._turn()  # the opening turn: addressed, answered
    await session._turn()  # side conversation: ignored entirely
    assert [text for text, _ in orch.heard] == ["sutra, what is the weather"]
    assert speaker.said == ["Sunny."]
