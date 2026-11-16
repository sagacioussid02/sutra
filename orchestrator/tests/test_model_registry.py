"""The model registry: one role -> model mapping, flippable per role by env.

Defaults must preserve today's behavior exactly. A flip must reach the
model the API actually gets called with — for the Anthropic roles and
for the voice engines — without touching code.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import anthropic
import httpx2 as httpx
import pytest

from sutra_orchestrator.config import load_config
from sutra_orchestrator.model import AnthropicModel
from sutra_orchestrator.models import (
    REGISTRY,
    default_model,
    model_env_var,
    resolve_model,
    roles,
    spec,
)
from sutra_orchestrator.voice.config import load_voice_config
from sutra_orchestrator.voice.local_engines import FasterWhisperTranscriber
from sutra_orchestrator.voice.openai_engines import OpenAISpeaker, OpenAITranscriber


# Today's models, as the code used them before the registry existed.
# If any of these change, the change is a model swap, not a refactor.
EXPECTED_DEFAULTS = {
    "conversation": "claude-sonnet-5-5",
    "classifier": "claude-haiku-5-5",
    "extractor": "claude-haiku-5-5",
    "agent": "claude-haiku-5-5",
    "stt": "gpt-4o-transcribe",
    "tts": "gpt-4o-mini-tts",
    "local_stt": "base.en",
}

EXPECTED_ENV_VARS = {
    "conversation": "SUTRA_MODEL",
    "classifier": "SUTRA_CLASSIFIER_MODEL",
    "extractor": "SUTRA_EXTRACTOR_MODEL",
    "agent": "SUTRA_AGENT_MODEL",
    "stt": "SUTRA_STT_MODEL",
    "tts": "SUTRA_TTS_MODEL",
    "local_stt": "SUTRA_LOCAL_STT_MODEL",
}

BASE_ENV = {"SUTRA_TOKEN": "t", "ANTHROPIC_API_KEY": "k"}


def test_registry_covers_exactly_the_roles_the_code_uses():
    assert set(roles()) == set(EXPECTED_DEFAULTS)
    for role, default in EXPECTED_DEFAULTS.items():
        entry = spec(role)
        assert entry.default == default
        assert entry.env_var == EXPECTED_ENV_VARS[role]
        assert entry.provider in ("anthropic", "openai", "faster-whisper")
        assert default_model(role) == default
        assert model_env_var(role) == EXPECTED_ENV_VARS[role]


def test_defaults_are_preserved_through_the_config_loaders():
    config = load_config(env=dict(BASE_ENV), dotenv_path=None)
    assert config.model == "claude-sonnet-5-5"
    assert config.classifier_model == "claude-haiku-5-5"
    assert config.extractor_model == "claude-haiku-5-5"
    assert config.agent_model == "claude-haiku-5-5"

    voice = load_voice_config(env={}, dotenv_path=None)
    assert voice.stt_model == "gpt-4o-transcribe"
    assert voice.tts_model == "gpt-4o-mini-tts"
    assert voice.local_stt_model == "base.en"


def test_each_role_flips_by_its_own_env_var_and_nothing_else():
    for role, flipped in EXPECTED_DEFAULTS.items():
        flipped = flipped + "-flipped"
        env = {EXPECTED_ENV_VARS[role]: flipped}
        assert resolve_model(role, env) == flipped
        # Every other role is untouched by this role's variable.
        for other in EXPECTED_DEFAULTS:
            if other != role:
                assert resolve_model(other, env) == EXPECTED_DEFAULTS[other]


def test_a_blank_env_value_counts_as_unset():
    for role in EXPECTED_DEFAULTS:
        assert resolve_model(role, {EXPECTED_ENV_VARS[role]: "   "}) == EXPECTED_DEFAULTS[role]


def test_unknown_role_is_an_error_not_a_silent_default():
    with pytest.raises(ValueError, match="unknown model role"):
        resolve_model("nope")
    with pytest.raises(ValueError, match="unknown model role"):
        default_model("nope")


def test_config_flip_reaches_every_anthropic_role():
    env = dict(
        BASE_ENV,
        SUTRA_MODEL="claude-opus-5-5",
        SUTRA_CLASSIFIER_MODEL="claude-haiku-5-5-flipped",
        SUTRA_EXTRACTOR_MODEL="claude-sonnet-5-5-flipped",
        SUTRA_AGENT_MODEL="claude-opus-5-5-flipped",
    )
    config = load_config(env=env, dotenv_path=None)
    assert config.model == "claude-opus-5-5"
    assert config.classifier_model == "claude-haiku-5-5-flipped"
    assert config.extractor_model == "claude-sonnet-5-5-flipped"
    assert config.agent_model == "claude-opus-5-5-flipped"


def test_voice_config_flip_reaches_every_voice_role():
    env = {
        "SUTRA_STT_MODEL": "gpt-4o-transcribe-flipped",
        "SUTRA_TTS_MODEL": "gpt-4o-mini-tts-flipped",
        "SUTRA_LOCAL_STT_MODEL": "small",
    }
    voice = load_voice_config(env=env, dotenv_path=None)
    assert voice.stt_model == "gpt-4o-transcribe-flipped"
    assert voice.tts_model == "gpt-4o-mini-tts-flipped"
    assert voice.local_stt_model == "small"


# --- end to end: the flipped model is the one sent to the API -------------


def _message(content, stop_reason="end_turn"):
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


def _model_from_flipped_config(handler):
    """An AnthropicModel built from a flipped config, on a mocked transport."""
    sent: list[dict] = []

    def wrapped(request: httpx.Request) -> httpx.Response:
        sent.append(json.loads(request.content))
        return handler(request)

    config = load_config(
        env=dict(
            BASE_ENV,
            SUTRA_MODEL="claude-opus-5-5",
            SUTRA_CLASSIFIER_MODEL="claude-haiku-5-5-flipped",
            SUTRA_EXTRACTOR_MODEL="claude-sonnet-5-5-flipped",
            SUTRA_AGENT_MODEL="claude-opus-5-5-flipped",
        ),
        dotenv_path=None,
    )
    model = AnthropicModel(
        config.api_key,
        config.model,
        config.classifier_model,
        extractor_model=config.extractor_model,
        agent_model=config.agent_model,
    )
    model._client = anthropic.AsyncAnthropic(
        api_key="sk-test", http_client=httpx.AsyncClient(transport=httpx.MockTransport(wrapped))
    )
    return model, sent


async def test_flipped_models_are_the_ones_sent_to_anthropic():
    model, sent = _model_from_flipped_config(
        lambda r: _message([{"type": "text", "text": "hi"}])
    )
    await model.complete(
        system="s", messages=[{"role": "user", "content": "hi"}], tools=[]
    )
    assert sent[-1]["model"] == "claude-opus-5-5"  # conversation


async def test_flipped_classifier_model_is_the_one_sent():
    model, sent = _model_from_flipped_config(
        lambda r: _message(
            [{"type": "tool_use", "id": "t1", "name": "classify", "input": {"label": "affirm"}}],
            "tool_use",
        )
    )
    assert await model.classify(system="s", user="yes") == "affirm"
    assert sent[-1]["model"] == "claude-haiku-5-5-flipped"  # classifier


async def test_flipped_extractor_model_is_the_one_sent_for_extract_and_structured():
    def handler(request):
        body = json.loads(request.content)
        tool = body["tools"][0]["name"]
        if tool == "record_statements":
            content = [{"type": "tool_use", "id": "t1", "name": tool, "input": {"statements": []}}]
        else:  # record_episode
            content = [{"type": "tool_use", "id": "t1", "name": tool, "input": {"keep": False}}]
        return _message(content, "tool_use")

    model, sent = _model_from_flipped_config(handler)
    await model.extract(system="s", user="I like tea")
    assert sent[-1]["model"] == "claude-sonnet-5-5-flipped"  # extractor
    await model.structured(name="episode", system="s", user="we talked")
    assert sent[-1]["model"] == "claude-sonnet-5-5-flipped"  # structured rides the extractor


async def test_flipped_agent_model_is_the_one_sent_for_research():
    model, sent = _model_from_flipped_config(
        lambda r: _message([{"type": "text", "text": "found it"}])
    )
    await model.research_step(
        system="s", messages=[{"role": "user", "content": "q"}], tools=[],
        max_searches=1, max_tokens=100,
    )
    assert sent[-1]["model"] == "claude-opus-5-5-flipped"  # agent


# --- end to end: voice engines --------------------------------------------


async def test_flipped_voice_models_are_the_ones_sent_to_openai():
    seen_stt: dict = {}

    class Transcriptions:
        async def create(self, **kw):
            seen_stt.update(kw)
            return SimpleNamespace(text="hi", logprobs=None)

    voice = load_voice_config(
        env={"SUTRA_STT_MODEL": "gpt-4o-transcribe-flipped", "SUTRA_TTS_MODEL": "gpt-4o-mini-tts-flipped"},
        dotenv_path=None,
    )
    client = SimpleNamespace(audio=SimpleNamespace(transcriptions=Transcriptions()))
    await OpenAITranscriber("k", voice.stt_model, client=client).transcribe(b"wav")
    assert seen_stt["model"] == "gpt-4o-transcribe-flipped"

    seen_tts: dict = {}

    class Stream:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def iter_bytes(self, size):
            yield b"\x01\x00"

    class Speech:
        class with_streaming_response:  # noqa: N801
            @staticmethod
            def create(**kw):
                seen_tts.update(kw)
                return Stream()

    async def play(chunks):
        async for _ in chunks:
            pass

    tts_client = SimpleNamespace(audio=SimpleNamespace(speech=Speech()))
    await OpenAISpeaker("k", voice.tts_model, client=tts_client, play=play).say("hi")
    assert seen_tts["model"] == "gpt-4o-mini-tts-flipped"


def test_engine_defaults_come_from_the_registry():
    assert OpenAITranscriber("k")._model == "gpt-4o-transcribe"
    assert OpenAISpeaker("k")._model == "gpt-4o-mini-tts"
    assert FasterWhisperTranscriber()._size == "base.en"
    assert REGISTRY["local_stt"].default == "base.en"
