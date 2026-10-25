"""Config, the REPL, and secret handling (tasks 1.4, 6.x, 7.14)."""

from __future__ import annotations

import logging

import pytest

from sutra_orchestrator.config import load_config
from sutra_orchestrator.errors import ConfigError
from sutra_orchestrator.repl import configure_logging, run_repl

from .fakes import FakeGateway, FakeModel, default_tools, make_orchestrator, ok, pending, resp, text, tool_use

TOKEN = "tok-0daafeb5166676dae18d127ef78033e36d517f4ec6f2103d02368ac8e1749717"
API_KEY = "sk-ant-THIS-IS-A-SECRET-KEY-123"


# --- config --------------------------------------------------------------------------------


def test_missing_required_variables_are_named():
    with pytest.raises(ConfigError) as err:
        load_config(env={}, dotenv_path=None)
    message = str(err.value)
    assert "SUTRA_TOKEN" in message and "ANTHROPIC_API_KEY" in message

    with pytest.raises(ConfigError) as err:
        load_config(env={"SUTRA_TOKEN": "t"}, dotenv_path=None)
    assert "ANTHROPIC_API_KEY" in str(err.value) and "SUTRA_TOKEN" not in str(err.value)


def test_defaults_and_overrides():
    config = load_config(env={"SUTRA_TOKEN": "t", "ANTHROPIC_API_KEY": "k"}, dotenv_path=None)
    assert config.gateway_url == "http://127.0.0.1:8765"
    assert config.model == "claude-sonnet-5-5"
    assert config.classifier_model == "claude-haiku-5-5"
    assert config.max_tool_calls == 6

    config = load_config(
        env={
            "SUTRA_TOKEN": "t",
            "ANTHROPIC_API_KEY": "k",
            "SUTRA_GATEWAY_URL": "http://gw:1",
            "SUTRA_MODEL": "claude-opus-5-5",
            "SUTRA_MAX_TOOL_CALLS": "3",
        },
        dotenv_path=None,
    )
    assert (config.gateway_url, config.model, config.max_tool_calls) == (
        "http://gw:1",
        "claude-opus-5-5",
        3,
    )


def test_invalid_integer_setting_is_a_clear_error():
    with pytest.raises(ConfigError, match="SUTRA_MAX_TOOL_CALLS"):
        load_config(
            env={"SUTRA_TOKEN": "t", "ANTHROPIC_API_KEY": "k", "SUTRA_MAX_TOOL_CALLS": "lots"},
            dotenv_path=None,
        )


def test_dotenv_file_is_read_and_real_environment_wins(tmp_path, monkeypatch):
    dotenv = tmp_path / ".env"
    dotenv.write_text("SUTRA_TOKEN=from-file\nANTHROPIC_API_KEY=key-from-file\n")
    monkeypatch.delenv("SUTRA_TOKEN", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    config = load_config(dotenv_path=dotenv)
    assert (config.token, config.api_key) == ("from-file", "key-from-file")

    monkeypatch.setenv("SUTRA_TOKEN", "from-env")
    assert load_config(dotenv_path=dotenv).token == "from-env"


def test_config_repr_does_not_contain_secrets():
    config = load_config(env={"SUTRA_TOKEN": TOKEN, "ANTHROPIC_API_KEY": API_KEY}, dotenv_path=None)
    assert TOKEN not in repr(config) and API_KEY not in repr(config)


# --- 7.14: verbose logging never contains the secrets --------------------------------------------


async def test_verbose_logs_show_tools_and_timings_but_never_secrets(capsys):
    configure_logging(verbose=True, secrets=[TOKEN, API_KEY])
    model = FakeModel([resp(tool_use("finanxe_list_debts")), resp(text("done"))])
    gateway = FakeGateway(tools=default_tools(), results={"finanxe_list_debts": ok({"d": 1})})
    orch, _ = await make_orchestrator(model, gateway)

    await orch.respond("my debts?")
    logging.getLogger("sutra_orchestrator").warning("something leaked %s and %s", TOKEN, API_KEY)

    err = capsys.readouterr().err
    assert "finanxe_list_debts" in err and "model call took" in err
    assert TOKEN not in err and API_KEY not in err
    assert "[redacted]" in err


# --- REPL -----------------------------------------------------------------------------------------


class Typed:
    def __init__(self, *lines):
        self.lines = list(lines)
        self.prompts = []

    async def __call__(self, prompt):
        self.prompts.append(prompt)
        if not self.lines:
            raise EOFError
        return self.lines.pop(0)


async def test_repl_prints_each_reply_and_stops_on_a_blank_line():
    model = FakeModel([resp(text("first")), resp(text("second"))])
    orch, _ = await make_orchestrator(model)
    out = []

    await run_repl(orch, read=Typed("one", "two", "", "never reached"), out=out.append)

    assert out == ["sutra> first", "sutra> second"]
    assert len(model.calls) == 2


async def test_repl_stops_cleanly_on_end_of_input():
    model = FakeModel([resp(text("only"))])
    orch, _ = await make_orchestrator(model)
    out = []
    await run_repl(orch, read=Typed("hello"), out=out.append)  # then EOF
    assert out == ["sutra> only"]


async def test_repl_shows_the_gateways_description_and_expiry_under_a_readback():
    model = FakeModel([resp(tool_use("finanxe_create_goal")), resp(text("Shall I do that?"))])
    gateway = FakeGateway(tools=default_tools(), results={"finanxe_create_goal": pending()})
    orch, _ = await make_orchestrator(model, gateway)
    out = []

    await run_repl(orch, read=Typed("make a goal"), out=out.append)

    assert out[0] == "sutra> Shall I do that?"
    assert out[1] == "  pending: Create a goal named Vacation for 2000 dollars."
    assert out[2].startswith("  expires: ")


async def test_repl_does_not_repeat_the_pending_description_on_a_reask():
    model = FakeModel([resp(tool_use("finanxe_create_goal")), resp(text("Shall I?"))])
    gateway = FakeGateway(tools=default_tools(), results={"finanxe_create_goal": pending()})
    orch, _ = await make_orchestrator(model, gateway)
    out = []

    await run_repl(orch, read=Typed("make a goal", "hmm"), out=out.append)

    assert sum(1 for line in out if line.startswith("  pending:")) == 1
