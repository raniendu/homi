"""Argument parsing tests for Homi CLI."""

from __future__ import annotations

import sys

import pytest

from homi.homi import parse_args, resolve_initial_prompt


def test_parse_prompt_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["homi", "--prompt", "Prompt text"])
    args = parse_args()
    assert args.prompt_text == "Prompt text"
    assert resolve_initial_prompt(args) == "Prompt text"


def test_positional_prompt_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["homi", "Prompt", "text"])
    args = parse_args()
    assert args.prompt_tokens == ["Prompt", "text"]
    assert resolve_initial_prompt(args) == "Prompt text"


def test_prompt_flag_precedence_over_positional(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        ["homi", "--prompt", "flag prompt", "positional", "prompt"],
    )
    args = parse_args()
    assert resolve_initial_prompt(args) == "flag prompt"


def test_oneshot_requires_prompt(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["homi", "--oneshot"])
    with pytest.raises(SystemExit) as excinfo:
        parse_args()
    assert excinfo.value.code == 2


def test_json_requires_oneshot(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["homi", "--prompt", "hello", "--json"])
    with pytest.raises(SystemExit) as excinfo:
        parse_args()
    assert excinfo.value.code == 2
