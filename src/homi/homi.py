"""Homi CLI interface powered by Strands and configurable model providers."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from datetime import datetime, timezone
from typing import Any

from rich.text import Text
from strands import Agent
from strands.models.ollama import OllamaModel
from strands_tools import calculator, current_time, http_request
from textual import on, work
from textual.app import App, ComposeResult
from textual.widgets import Footer, Header, Input, RichLog, Static

try:
    from homi.config import DEFAULT_CONFIG_PATH, AgentConfig, resolve_agent_config
except ModuleNotFoundError:  # pragma: no cover - script-path import fallback
    from config import DEFAULT_CONFIG_PATH, AgentConfig, resolve_agent_config

EXIT_COMMANDS = {"/quit", "/exit", "/q"}
CLEAR_COMMAND = "/clear"
DEFAULT_TOOLS = [current_time, calculator, http_request]


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Run Homi CLI, a terminal chat interface with configurable model provider."
    )
    parser.add_argument(
        "prompt_tokens",
        nargs="*",
        help="Optional initial prompt submitted after the interface loads.",
    )
    parser.add_argument(
        "--prompt",
        dest="prompt_text",
        default=None,
        help="Prompt text for initial message or one-shot mode.",
    )
    parser.add_argument(
        "--config",
        default=os.getenv("HOMI_CONFIG", DEFAULT_CONFIG_PATH),
        help=(
            "Path to config JSON file "
            f"(default: {DEFAULT_CONFIG_PATH}, override with HOMI_CONFIG env var)."
        ),
    )
    parser.add_argument(
        "--host",
        "--endpoint",
        dest="endpoint",
        default=None,
        help="Model endpoint/host override.",
    )
    parser.add_argument(
        "--provider",
        default=None,
        help="Model provider override (for example: ollama).",
    )
    parser.add_argument(
        "--model",
        dest="model_id",
        default=None,
        help="Model ID override.",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=None,
        help="Temperature override for model generation.",
    )
    parser.add_argument(
        "--thinking-effort",
        default=None,
        help=(
            "Reasoning/thinking effort preference (for example: high/medium/low). "
            "Applied only when supported by the selected provider/model integration."
        ),
    )
    parser.add_argument(
        "--system-prompt",
        default=None,
        help="System prompt override for the agent.",
    )
    parser.add_argument(
        "--oneshot",
        action="store_true",
        help="Run a single prompt/response interaction and exit without launching the TUI.",
    )
    parser.add_argument(
        "--json",
        dest="json_output",
        action="store_true",
        help="Emit one-shot output as JSON (requires --oneshot).",
    )
    parsed = parser.parse_args()
    initial_prompt = resolve_initial_prompt(parsed)
    if parsed.json_output and not parsed.oneshot:
        parser.error("--json requires --oneshot.")
    if parsed.oneshot and not initial_prompt:
        parser.error(
            "--oneshot requires a prompt via --prompt or positional prompt text."
        )
    return parsed


def resolve_initial_prompt(args: argparse.Namespace) -> str | None:
    """Resolve the initial prompt from CLI flags and positional tokens."""
    if args.prompt_text is not None:
        normalized_prompt_text = args.prompt_text.strip()
        return normalized_prompt_text or None

    positional_prompt = " ".join(args.prompt_tokens).strip()
    return positional_prompt or None


def format_oneshot_output(
    *,
    prompt: str,
    raw_response: Any,
    config: AgentConfig,
    json_output: bool,
) -> str:
    """Format one-shot mode output for plain text or JSON use cases."""
    response_text = format_message_for_display(raw_response)
    if not json_output:
        return normalize_inline_markdown(response_text)

    payload = {
        "prompt": prompt,
        "response": response_text,
        "provider": config.provider,
        "model_id": config.model_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    return json.dumps(payload, ensure_ascii=False)


def build_provider_hint(config: AgentConfig | None, args: argparse.Namespace) -> str:
    """Generate provider-specific runtime troubleshooting guidance."""
    model_hint = (
        args.model_id
        or os.getenv("HOMI_MODEL_ID")
        or os.getenv("OLLAMA_MODEL")
        or "configured model"
    )
    if config and config.provider.lower() == "ollama":
        return (
            f"Ensure Ollama is running at '{config.endpoint}' "
            f"and model '{config.model_id}' is pulled."
        )

    provider_name = config.provider if config else (args.provider or "configured")
    return (
        f"Check connectivity/auth for provider '{provider_name}' "
        f"and model '{model_hint}'."
    )


def format_message_for_display(message: Any) -> str:
    """Convert structured agent messages into readable chat text."""
    if isinstance(message, str):
        return message

    text_chunks: list[str] = []

    def collect_text(node: Any) -> None:
        if isinstance(node, dict):
            text_value = node.get("text")
            if isinstance(text_value, str) and text_value.strip():
                text_chunks.append(text_value.strip())

            # Common Strands message fields that may carry nested text blocks.
            if "content" in node:
                collect_text(node["content"])
            if "toolResult" in node:
                collect_text(node["toolResult"])
            return

        if isinstance(node, list):
            for item in node:
                collect_text(item)

    collect_text(message)
    if text_chunks:
        return "\n\n".join(text_chunks)

    # Fallback: keep non-text payloads visible for debugging / machine-oriented responses.
    return json.dumps(message, indent=2, ensure_ascii=False)


def normalize_inline_markdown(text: str) -> str:
    """Normalize common markdown wrappers into plain inline text for chat display."""
    normalized = text.replace("\r\n", "\n")

    # Fenced code blocks -> just code contents.
    normalized = re.sub(
        r"```(?:[a-zA-Z0-9_+\-]+)?\n?(.*?)\n?```",
        lambda m: m.group(1).strip(),
        normalized,
        flags=re.DOTALL,
    )
    # Inline code -> plain text.
    normalized = re.sub(r"`([^`]+)`", r"\1", normalized)
    # Markdown links -> "label (url)".
    normalized = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1 (\2)", normalized)
    # Common emphasis markers.
    normalized = re.sub(r"(?<!\*)\*\*(?=\S)(.+?)(?<=\S)\*\*(?!\*)", r"\1", normalized)
    normalized = re.sub(r"(?<!_)__(?=\S)(.+?)(?<=\S)__(?!_)", r"\1", normalized)
    normalized = re.sub(r"(?<!\*)\*(?=\S)(.+?)(?<=\S)\*(?!\*)", r"\1", normalized)
    normalized = re.sub(r"(?<!_)_(?=\S)(.+?)(?<=\S)_(?!_)", r"\1", normalized)
    normalized = re.sub(r"~~(?=\S)(.+?)(?<=\S)~~", r"\1", normalized)

    return normalized.strip()


class HomiSession:
    """Manages the conversational agent lifecycle and memory."""

    def __init__(self, config: AgentConfig) -> None:
        self.config = config
        self.agent = self._build_agent()

    def _build_model(self) -> Any:
        provider = self.config.provider.lower()

        if provider == "ollama":
            model_kwargs: dict[str, Any] = {"model_id": self.config.model_id}
            if self.config.endpoint:
                model_kwargs["host"] = self.config.endpoint
            if self.config.temperature is not None:
                model_kwargs["temperature"] = self.config.temperature

            reserved_keys = {"model_id", "host", "temperature"}
            model_kwargs.update(
                {
                    key: value
                    for key, value in self.config.model_params.items()
                    if key not in reserved_keys
                }
            )
            self._apply_thinking_effort_if_supported(
                model_kwargs=model_kwargs,
                supported_keys=set(OllamaModel.OllamaConfig.__annotations__.keys()),
            )
            return OllamaModel(**model_kwargs)

        raise ValueError(
            f"Unsupported model provider '{self.config.provider}'. Currently supported: ollama."
        )

    def _apply_thinking_effort_if_supported(
        self, *, model_kwargs: dict[str, Any], supported_keys: set[str]
    ) -> None:
        effort = self.config.thinking_effort
        if not effort:
            return

        for candidate_key in ("thinking_effort", "reasoning_effort", "effort"):
            if candidate_key in supported_keys and candidate_key not in model_kwargs:
                model_kwargs[candidate_key] = effort
                return

    def _build_agent(self) -> Agent:
        model = self._build_model()
        agent_kwargs: dict[str, Any] = {
            "model": model,
            "callback_handler": None,
            "tools": DEFAULT_TOOLS,
        }
        if self.config.system_prompt:
            agent_kwargs["system_prompt"] = self.config.system_prompt

        return Agent(**agent_kwargs)

    def clear(self) -> None:
        """Reset conversation state by recreating the underlying agent."""
        self.agent = self._build_agent()

    def reply(self, prompt: str) -> Any:
        """Send a user message to the model and return the raw assistant payload."""
        result = self.agent(prompt)
        return result.message


class HomiTerminalApp(App[None]):
    """Textual-based terminal interface for Homi."""

    TITLE = "Homi CLI"
    SUB_TITLE = "Textual"
    theme = "textual-light"

    CSS = """
    Screen {
        layout: vertical;
        padding: 0 1;
        background: #E0E0E0;
    }

    Header {
        dock: top;
        background: #E0E0E0;
        color: #2f2f2f;
    }

    Footer {
        dock: bottom;
        background: #E0E0E0;
        color: #4a4a4a;
    }

    #brand_header {
        border: round #bdbdbd;
        padding: 0 2;
        content-align: center middle;
        text-style: bold;
        height: 3;
        margin: 1 1 0 1;
        background: #ffffff;
        color: #004578;
    }

    #model_header {
        border: round #0178D4;
        padding: 0 2;
        content-align: center middle;
        text-style: bold;
        height: 3;
        margin: 1 1 0 1;
        background: #EEF6FF;
        color: #004578;
    }

    #chat_log {
        height: 1fr;
        border: round #bdbdbd;
        padding: 0 1;
        margin: 1;
        background: #ffffff;
        color: #2f2f2f;
    }

    #chat_log:focus {
        border: round #0178D4;
    }

    #chat_input {
        margin: 0 1 1 1;
        border: round #bdbdbd;
        background: #ffffff;
        color: #2f2f2f;
    }

    #chat_input:focus {
        border: round #2383e2;
    }
    """

    BINDINGS = [
        ("ctrl+c", "quit", "Quit"),
        ("ctrl+l", "clear_chat_log", "Clear Log"),
    ]

    def __init__(self, session: HomiSession, initial_prompt: str | None = None) -> None:
        super().__init__()
        self.session = session
        self.initial_prompt = initial_prompt

    def compose(self) -> ComposeResult:
        title_text = Text("HOMI CLI", style="bold #004578")
        title_text.justify = "center"

        model_text = Text()
        model_text.append(" MODEL ", style="bold #004578 on #dceeff")
        model_text.append(f" {self.session.config.model_id}  ", style="bold #004578")
        model_text.append(" PROVIDER ", style="bold #004578 on #dceeff")
        model_text.append(f" {self.session.config.provider}  ", style="#36506a")
        model_text.append(" TEMP ", style="bold #004578 on #dceeff")
        if self.session.config.temperature is None:
            model_text.append(" n/a  ", style="#36506a")
        else:
            model_text.append(
                f" {self.session.config.temperature:.2f}  ", style="#36506a"
            )
        model_text.append(" THINK ", style="bold #004578 on #dceeff")
        if self.session.config.thinking_effort:
            model_text.append(
                f" {self.session.config.thinking_effort}  ", style="#36506a"
            )
        else:
            model_text.append(" n/a  ", style="#36506a")
        if self.session.config.endpoint:
            model_text.append(" ENDPOINT ", style="bold #004578 on #dceeff")
            model_text.append(f" {self.session.config.endpoint} ", style="#36506a")
        model_text.justify = "center"

        yield Header(show_clock=True)
        yield Static(title_text, id="brand_header")
        yield Static(model_text, id="model_header")
        yield RichLog(id="chat_log", markup=False, highlight=False, wrap=True)
        yield Input(
            placeholder="Message Homi... (/clear, /q, /quit, /exit, !command)",
            id="chat_input",
        )
        yield Footer()

    def on_mount(self) -> None:
        temp_value = (
            f"{self.session.config.temperature:.2f}"
            if self.session.config.temperature is not None
            else "n/a"
        )
        thinking_value = self.session.config.thinking_effort or "n/a"
        self.sub_title = (
            f"{self.session.config.provider}:{self.session.config.model_id} "
            f"| Temp: {temp_value} | Thinking: {thinking_value}"
        )
        self._write_system("Homi is ready.")
        self._write_system(
            "Commands: /clear resets memory, /q /quit /exit close Homi, !<command> runs shell in TUI."
        )
        self._write_system(
            "Security: !<command> executes in your local shell and is intended for trusted local environments."
        )
        self._write_system("Loaded tools: current_time, calculator, http_request.")
        if self.session.config.system_prompt:
            self._write_system("System prompt loaded from configuration.")
        self.query_one("#chat_input", Input).focus()

        if self.initial_prompt:
            self.call_after_refresh(self._submit_message, self.initial_prompt, True)

    @on(Input.Submitted, "#chat_input")
    def on_input_submitted(self, event: Input.Submitted) -> None:
        submitted = event.value.strip()
        event.input.value = ""
        self._submit_message(submitted, echo_user=True)

    def _set_busy(self, busy: bool) -> None:
        input_widget = self.query_one("#chat_input", Input)
        input_widget.disabled = busy
        if busy:
            input_widget.placeholder = "Homi is thinking..."
        else:
            input_widget.placeholder = (
                "Message Homi... (/clear, /q, /quit, /exit, !command)"
            )
            input_widget.focus()

    def _write_message(self, speaker: str, message: str) -> None:
        timestamp = datetime.now().strftime("%H:%M")
        prefix = Text(f"[{timestamp}] ", style="dim #7a7a7a")

        if speaker == "You":
            speaker_text = Text("You", style="bold #0178D4")
        elif speaker == "Homi":
            speaker_text = Text("Homi", style="bold #2f2f2f")
        elif speaker == "Shell":
            speaker_text = Text("Shell", style="bold #a45f00")
        else:
            speaker_text = Text(speaker, style="bold #555555")

        header = Text()
        header.append_text(prefix)
        header.append_text(speaker_text)
        header.append(": ", style="bold")

        log = self.query_one("#chat_log", RichLog)
        if speaker == "Homi":
            message = normalize_inline_markdown(message)

        body = Text(message, style="#2f2f2f")
        line = Text()
        line.append_text(header)
        line.append_text(body)
        log.write(line)
        log.write("")

    def _write_system(self, message: str) -> None:
        timestamp = datetime.now().strftime("%H:%M")
        text = Text()
        text.append(f"[{timestamp}] ", style="dim #7a7a7a")
        text.append("System", style="bold #6b6b6b")
        text.append(": ", style="bold")
        text.append(message, style="#555555")
        self.query_one("#chat_log", RichLog).write(text)

    @staticmethod
    def _format_shell_output(
        command: str, stdout: str, stderr: str, return_code: int
    ) -> str:
        lines = [f"$ {command}"]

        clean_stdout = stdout.rstrip()
        clean_stderr = stderr.rstrip()

        if clean_stdout:
            lines.append(clean_stdout)
        if clean_stderr:
            lines.append("[stderr]")
            lines.append(clean_stderr)
        if not clean_stdout and not clean_stderr:
            lines.append("(no output)")

        lines.append(f"[exit {return_code}]")
        return "\n".join(lines)

    def _submit_message(self, raw_input: str, echo_user: bool) -> None:
        user_input = raw_input.strip()
        if not user_input:
            return

        if echo_user:
            self._write_message("You", user_input)

        command = user_input.lower()
        if command in EXIT_COMMANDS:
            self._write_system("Exiting Homi.")
            self.exit()
            return

        if command == CLEAR_COMMAND:
            try:
                self.session.clear()
            except Exception as exc:  # pragma: no cover - runtime integration guard
                self._write_system(
                    f"Homi error: unable to clear conversation state: {exc}"
                )
                return
            self._write_system("Conversation state cleared.")
            return

        # TUI-only shell escape. Other interfaces do not use this path.
        if user_input.startswith("!"):
            shell_command = user_input[1:].strip()
            if not shell_command:
                self._write_system("Shell command is empty. Use !<command>.")
                return
            self._set_busy(True)
            self._run_shell_command(shell_command)
            return

        self._set_busy(True)
        self._run_agent(user_input)

    def action_clear_chat_log(self) -> None:
        """Clear only the visible chat log, preserving conversation state."""
        log = self.query_one("#chat_log", RichLog)
        log.clear()
        self._write_system("Chat log cleared. Conversation memory is unchanged.")

    @work(thread=True)
    def _run_agent(self, prompt: str) -> None:
        try:
            raw_response = self.session.reply(prompt)
            response = format_message_for_display(raw_response)
        except Exception as exc:  # pragma: no cover - runtime integration guard
            self.call_from_thread(self._write_system, f"Homi error: {exc}")
        else:
            self.call_from_thread(self._write_message, "Homi", response)
        finally:
            self.call_from_thread(self._set_busy, False)

    @work(thread=True)
    def _run_shell_command(self, command: str) -> None:
        try:
            # Intentional: shell=True preserves shell syntax (pipes/redirection) for the
            # explicit TUI shell escape feature. This is trusted-local usage only.
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=60,
            )
        except subprocess.TimeoutExpired:
            self.call_from_thread(
                self._write_system, f"Shell command timed out after 60s: {command}"
            )
        except Exception as exc:  # pragma: no cover - runtime integration guard
            self.call_from_thread(self._write_system, f"Shell execution error: {exc}")
        else:
            output = self._format_shell_output(
                command=command,
                stdout=result.stdout,
                stderr=result.stderr,
                return_code=result.returncode,
            )
            self.call_from_thread(self._write_message, "Shell", output)
        finally:
            self.call_from_thread(self._set_busy, False)


def main() -> None:
    args = parse_args()
    initial_prompt = resolve_initial_prompt(args)
    config: AgentConfig | None = None

    try:
        config = resolve_agent_config(
            config_path=args.config,
            provider_override=args.provider,
            host_override=args.endpoint,
            model_override=args.model_id,
            temperature_override=args.temperature,
            thinking_effort_override=args.thinking_effort,
            system_prompt_override=args.system_prompt,
        )
        session = HomiSession(config=config)
    except ValueError as exc:
        raise SystemExit(f"Configuration error: {exc}") from exc
    except Exception as exc:  # pragma: no cover - runtime integration guard
        provider_hint = build_provider_hint(config, args)
        raise SystemExit(
            "Homi startup failed. " f"{provider_hint} Error: {exc}"
        ) from exc

    if args.oneshot:
        assert config is not None  # for type narrowing; set during startup success path
        assert initial_prompt is not None  # enforced by argument validation
        try:
            raw_response = session.reply(initial_prompt)
            output = format_oneshot_output(
                prompt=initial_prompt,
                raw_response=raw_response,
                config=config,
                json_output=args.json_output,
            )
        except Exception as exc:  # pragma: no cover - runtime integration guard
            provider_hint = build_provider_hint(config, args)
            raise SystemExit(
                "Homi one-shot failed. " f"{provider_hint} Error: {exc}"
            ) from exc
        print(output)
        return

    app = HomiTerminalApp(session=session, initial_prompt=initial_prompt)
    app.run()


if __name__ == "__main__":
    main()
