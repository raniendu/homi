"""One-shot and interactive mode behavior tests."""

from __future__ import annotations

import argparse
import json
from types import SimpleNamespace

import pytest

import homi.homi as homi_module


def _build_args(
    *, oneshot: bool, json_output: bool, prompt_text: str
) -> argparse.Namespace:
    return argparse.Namespace(
        prompt_tokens=[],
        prompt_text=prompt_text,
        config="homi.config.json",
        endpoint=None,
        provider=None,
        model_id=None,
        temperature=None,
        thinking_effort=None,
        system_prompt=None,
        oneshot=oneshot,
        json_output=json_output,
    )


def test_main_oneshot_plain_output(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config = SimpleNamespace(provider="ollama", model_id="gpt-oss", endpoint="local")

    class DummySession:
        def __init__(self, config: SimpleNamespace) -> None:
            self.config = config

        def reply(self, prompt: str) -> str:
            assert prompt == "hello"
            return "**pong**"

    monkeypatch.setattr(
        homi_module,
        "parse_args",
        lambda: _build_args(oneshot=True, json_output=False, prompt_text="hello"),
    )
    monkeypatch.setattr(homi_module, "resolve_agent_config", lambda **_: config)
    monkeypatch.setattr(homi_module, "HomiSession", DummySession)

    homi_module.main()
    captured = capsys.readouterr()
    assert captured.out == "pong\n"
    assert captured.err == ""


def test_main_oneshot_json_output(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config = SimpleNamespace(provider="ollama", model_id="gpt-oss", endpoint="local")

    class DummySession:
        def __init__(self, config: SimpleNamespace) -> None:
            self.config = config

        def reply(self, prompt: str) -> dict[str, object]:
            assert prompt == "status"
            return {"content": [{"text": "line one"}, {"text": "line two"}]}

    monkeypatch.setattr(
        homi_module,
        "parse_args",
        lambda: _build_args(oneshot=True, json_output=True, prompt_text="status"),
    )
    monkeypatch.setattr(homi_module, "resolve_agent_config", lambda **_: config)
    monkeypatch.setattr(homi_module, "HomiSession", DummySession)

    homi_module.main()
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["prompt"] == "status"
    assert payload["response"] == "line one\n\nline two"
    assert payload["provider"] == "ollama"
    assert payload["model_id"] == "gpt-oss"
    assert "timestamp" in payload
    assert captured.err == ""


def test_main_oneshot_runtime_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    config = SimpleNamespace(provider="ollama", model_id="gpt-oss", endpoint="local")

    class DummySession:
        def __init__(self, config: SimpleNamespace) -> None:
            self.config = config

        def reply(self, prompt: str) -> str:
            raise RuntimeError("boom")

    monkeypatch.setattr(
        homi_module,
        "parse_args",
        lambda: _build_args(oneshot=True, json_output=False, prompt_text="hello"),
    )
    monkeypatch.setattr(homi_module, "resolve_agent_config", lambda **_: config)
    monkeypatch.setattr(homi_module, "HomiSession", DummySession)

    with pytest.raises(SystemExit) as excinfo:
        homi_module.main()
    assert "Homi one-shot failed." in str(excinfo.value)


def test_main_non_oneshot_runs_tui(monkeypatch: pytest.MonkeyPatch) -> None:
    config = SimpleNamespace(provider="ollama", model_id="gpt-oss", endpoint="local")
    run_called: dict[str, object] = {"value": False, "initial_prompt": None}

    class DummySession:
        def __init__(self, config: SimpleNamespace) -> None:
            self.config = config

    class DummyTerminalApp:
        def __init__(self, session: DummySession, initial_prompt: str | None) -> None:
            run_called["initial_prompt"] = initial_prompt

        def run(self) -> None:
            run_called["value"] = True

    monkeypatch.setattr(
        homi_module,
        "parse_args",
        lambda: _build_args(oneshot=False, json_output=False, prompt_text="hello"),
    )
    monkeypatch.setattr(homi_module, "resolve_agent_config", lambda **_: config)
    monkeypatch.setattr(homi_module, "HomiSession", DummySession)
    monkeypatch.setattr(homi_module, "HomiTerminalApp", DummyTerminalApp)

    homi_module.main()
    assert run_called["initial_prompt"] == "hello"
    assert run_called["value"] is True
