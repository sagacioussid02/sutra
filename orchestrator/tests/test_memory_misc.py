"""Extractor parsing, text helpers, config options, the Anthropic extractor call, eval sets."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from sutra_orchestrator.config import load_config
from sutra_orchestrator.errors import ConfigError
from sutra_orchestrator.memstore import extractor as ex
from sutra_orchestrator.memstore.textutil import fts_query, normalize, overlap, tokens

from .test_anthropic_model import make_model, message

EVALS = Path(__file__).parent.parent / "evals"


# --- text helpers ---------------------------------------------------------------------------------------


def test_tokens_drop_stopwords_punctuation_and_duplicates():
    assert tokens("I get paid on the 15th, on the 15th!") == ["get", "paid", "15th"]
    assert tokens("Don't round my numbers") == ["dont", "round", "numbers"]


def test_overlap_needs_two_words_on_each_side_and_scores_updates_highly():
    assert overlap("I get paid on the 15th", "I get paid on the 1st") >= 0.6  # an updated fact
    assert overlap("My rent is 1200", "My rent is due on the 1st") < 0.6  # different facts
    assert overlap("I like dark mode", "I like short answers") < 0.6
    assert overlap("rent", "rent is due") == 0.0  # one word is never enough


def test_normalize_is_case_punctuation_and_apostrophe_insensitive():
    assert normalize("I get paid on the 15th.") == normalize("i get paid on THE 15th")
    assert normalize("Don't") == normalize("dont")


def test_fts_query_quotes_every_term_so_operators_are_inert():
    query = fts_query('rent AND "due" OR NEAR(x)')
    assert query is not None and all(part.startswith('"') for part in query.split(" OR "))
    assert fts_query("the and of") is None


# --- extractor parsing ----------------------------------------------------------------------------------


def test_parse_statements_accepts_good_rows_and_drops_bad_ones():
    out = ex.parse_statements(
        [
            {"content": "I get paid on the 15th.", "spoken": "You get paid on the 15th.", "kind": "fact"},
            {"content": "Keep it short.", "kind": "preference"},  # spoken missing: falls back
            {"content": "x", "spoken": "x", "kind": "fact"},  # too short
            {"content": "I am happy today.", "spoken": "You are happy.", "kind": "mood"},  # bad kind
            {"content": "y" * 400, "spoken": "y", "kind": "fact"},  # too long
            "not a dict",
        ]
    )
    assert [(s.content, s.spoken, s.kind) for s in out] == [
        ("I get paid on the 15th.", "You get paid on the 15th.", "fact"),
        ("Keep it short.", "Keep it short.", "preference"),
    ]
    assert ex.parse_statements("nope") == [] and ex.parse_statements(None) == []


def test_extractor_message_contains_only_the_two_user_messages():
    built = ex.build_user_message("  the current one  ", "the earlier one")
    assert "the current one" in built and "the earlier one" in built
    assert "(none)" in ex.build_user_message("hello", None)


def test_the_extractor_prompt_rules_out_credentials_and_manipulation():
    prompt = ex.system_prompt().lower()
    assert "credentials" in prompt and "not instructions" in prompt and "return nothing" in prompt


# --- config -----------------------------------------------------------------------------------------------


def test_memory_config_defaults_and_overrides():
    base = {"SUTRA_TOKEN": "t", "ANTHROPIC_API_KEY": "k"}
    config = load_config(env=base, dotenv_path=None)
    assert (config.memory_enabled, config.record_replies, config.episode_hot_days) == (True, True, 30)
    assert config.extractor_model == "claude-haiku-5-5" and config.memory_dir == "data"

    config = load_config(
        env={**base, "SUTRA_MEMORY": "off", "SUTRA_RECORD_REPLIES": "no", "SUTRA_EPISODE_HOT_DAYS": "7",
             "SUTRA_MEMORY_DIR": "/tmp/m", "SUTRA_EXTRACTOR_MODEL": "claude-sonnet-5-5"},
        dotenv_path=None,
    )
    assert (config.memory_enabled, config.record_replies, config.episode_hot_days) == (False, False, 7)
    assert (config.memory_dir, config.extractor_model) == ("/tmp/m", "claude-sonnet-5-5")


def test_bad_memory_switch_is_a_clear_error():
    with pytest.raises(ConfigError, match="SUTRA_MEMORY"):
        load_config(env={"SUTRA_TOKEN": "t", "ANTHROPIC_API_KEY": "k", "SUTRA_MEMORY": "maybe"}, dotenv_path=None)


# --- the Anthropic extractor call -------------------------------------------------------------------------


async def test_extract_forces_the_tool_and_uses_the_extractor_model():
    model, sent = make_model(
        lambda r: message(
            [{"type": "tool_use", "id": "t1", "name": "record_statements",
              "input": {"statements": [{"content": "I get paid on the 15th.", "spoken": "You get paid on the 15th.", "kind": "fact"}]}}],
            "tool_use",
        )
    )
    model._extractor_model = "claude-haiku-5-5"
    out = await model.extract(system="sys", user="msg")

    body = sent[0]
    assert out[0]["content"] == "I get paid on the 15th."
    assert body["model"] == "claude-haiku-5-5"
    assert body["tool_choice"] == {"type": "tool", "name": "record_statements"}
    assert body["messages"] == [{"role": "user", "content": "msg"}]


async def test_extract_without_a_tool_block_returns_nothing():
    model, _ = make_model(lambda r: message([{"type": "text", "text": "I remember things"}]))
    assert await model.extract(system="s", user="u") == []


# --- evaluation sets ---------------------------------------------------------------------------------------


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, EVALS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_extractor_set_is_well_formed_and_covers_the_required_cases():
    rows = [json.loads(line) for line in (EVALS / "extractor_messages.jsonl").read_text().splitlines() if line.strip()]
    assert len(rows) >= 40
    assert len({r["message"].lower() for r in rows}) == len(rows)
    positives = [r for r in rows if r["expect"] != "none"]
    assert all(r["expect"]["kinds"] and r["expect"]["must"] for r in positives)
    kinds = {k for r in positives for k in r["expect"]["kinds"]}
    assert kinds == set(ex.KINDS)
    assert any(r.get("tag") == "injection" for r in rows) and any(r.get("tag") == "credential" for r in rows)
    assert sum(1 for r in rows if r["expect"] == "none") >= 10  # transient, questions, bare answers


async def test_recall_quality_does_not_regress():
    """Keyword recall must keep serving ordinary questions and must not recall for unrelated ones."""
    assert await _load("run_recall_eval").main() == 0


def test_the_default_memory_directory_is_inside_the_orchestrator_not_the_cwd(tmp_path, monkeypatch):
    from sutra_orchestrator.__main__ import _memory_dir

    monkeypatch.chdir(tmp_path)
    resolved = _memory_dir("data")
    assert resolved == Path(__file__).resolve().parent.parent / "data"
    assert _memory_dir("/abs/elsewhere") == Path("/abs/elsewhere")
    assert _memory_dir("~/mem") == Path("~/mem").expanduser()
