"""Formatting helpers for one-shot and chat outputs."""

from __future__ import annotations

import json
from datetime import datetime
from types import SimpleNamespace

from homi.homi import (
    format_message_for_display,
    format_oneshot_output,
    normalize_inline_markdown,
)


def test_format_message_for_display_handles_nested_payload() -> None:
    message = {
        "content": [
            {"text": "first"},
            {"toolResult": {"content": [{"text": "second"}]}},
            {"content": [{"text": "third"}]},
        ]
    }
    assert format_message_for_display(message) == "first\n\nsecond\n\nthird"


def test_normalize_inline_markdown_common_cases() -> None:
    source = (
        "**Bold** and _italic_ and `inline`\n"
        "Link: [label](https://example.com)\n"
        "```bash\n"
        "echo hi\n"
        "```"
    )
    normalized = normalize_inline_markdown(source)
    assert "Bold" in normalized
    assert "italic" in normalized
    assert "inline" in normalized
    assert "label (https://example.com)" in normalized
    assert "echo hi" in normalized


def test_format_oneshot_output_json_payload() -> None:
    config = SimpleNamespace(provider="ollama", model_id="gpt-oss")
    output = format_oneshot_output(
        prompt='say "hi"',
        raw_response="line 1\nline 2",
        config=config,
        json_output=True,
    )
    payload = json.loads(output)
    assert payload["prompt"] == 'say "hi"'
    assert payload["response"] == "line 1\nline 2"
    assert payload["provider"] == "ollama"
    assert payload["model_id"] == "gpt-oss"
    datetime.fromisoformat(payload["timestamp"])
