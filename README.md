# Homi

Homi is a Strands chat agent with a Textual terminal interface.
For local development we start with Ollama, but config is provider-oriented so it can evolve to other providers later.

## Prerequisites

For local development with Ollama:

1. Install and run Ollama locally.
2. Pull at least one local model:

```bash
ollama pull gpt-oss:20b
```

3. Start the Ollama server:

```bash
ollama serve
```

## Install Dependencies

```bash
uv sync --dev
```

## Configuration

Agent runtime settings are now loaded from `homi.config.json`.
The configuration shape is provider-agnostic, while current code implementation supports `ollama`.

Default file:

```json
{
  "model": {
    "provider": "ollama",
    "model_id": "gpt-oss:20b",
    "endpoint": "http://localhost:11434",
    "temperature": 0.2,
    "params": {}
  },
  "agent": {
    "system_prompt": "You are Homi, a concise and practical assistant. The current date may be later than your internal knowledge cutoff. If a question is about current affairs, recent events, changing facts, or live data, look it up on the web first (using available web/http tools) before responding."
  }
}
```

Configuration precedence (highest to lowest):

1. CLI flags (`--provider`, `--model`, `--endpoint`, `--temperature`, `--system-prompt`)
2. Environment variables (`HOMI_MODEL_PROVIDER`, `HOMI_MODEL_ID`, `HOMI_MODEL_ENDPOINT`, `HOMI_MODEL_TEMPERATURE`, `HOMI_SYSTEM_PROMPT`)
3. Config file (`homi.config.json`)
4. Built-in defaults

Use a different config file path with:

- `--config path/to/file.json`
- or `HOMI_CONFIG=path/to/file.json`

## Run Homi

Start interactive chat with the default model (`gpt-oss:20b`):

```bash
uv run python src/homi/homi.py
```

When the CLI starts, you will see a `Homi` banner that includes:

- Agent name (`Homi`)
- Active model
- Active provider
- Temperature
- Model endpoint (when configured)

In chat mode:

- Type messages turn by turn.
- Use `!<command>` to run a local shell command directly from the TUI.
- Use `/clear` to reset conversation state.
- Use `/q`, `/quit`, or `/exit` to stop the session.
- Use `Ctrl+L` to clear only the visible chat log (conversation memory is preserved).

By default, Homi includes these Strands tools:

- `current_time`
- `calculator`
- `http_request`

Note: `!<command>` shell execution is implemented only in the Textual TUI input path.
Other interfaces do not execute shell commands from `!` prompts.

## Interface Design

The current runtime is split into:

- `HomiSession`: interface-agnostic agent/session orchestration (config, model, tools, memory reset).
- `HomiTerminalApp`: Textual TUI interface (rendering, input handling, slash commands, shell escape).

This separation is intentional so additional interfaces (for example REST/web) can reuse the same session logic without inheriting TUI-only behavior.

Start with an optional initial prompt, then continue chatting:

```bash
uv run python src/homi/homi.py "Give me three bullet points about Strands Agents."
```

Use a different local model or endpoint:

```bash
uv run python src/homi/homi.py --provider ollama --model mistral --endpoint http://localhost:11434 "Hello!"
```

Use a custom temperature:

```bash
uv run python src/homi/homi.py --temperature 0.4
```

Override the system prompt:

```bash
uv run python src/homi/homi.py --system-prompt "You are Homi. Keep answers short and technical."
```

You can also set environment variables instead of flags:

- `HOMI_CONFIG`
- `HOMI_MODEL_PROVIDER`
- `HOMI_MODEL_ID`
- `HOMI_MODEL_ENDPOINT`
- `HOMI_MODEL_TEMPERATURE`
- `HOMI_SYSTEM_PROMPT`

Compatibility note:

- Legacy env vars (`OLLAMA_MODEL`, `OLLAMA_HOST`, `OLLAMA_TEMPERATURE`) are still accepted as fallbacks.
