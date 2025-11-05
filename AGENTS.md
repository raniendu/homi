# Repository Guidelines

## Project Structure & Module Organization
- `packages/telegram/bot/`: DigitalOcean Functions action (Python web action).
- `packages/telegram/bot/bot.py`: Core logic to process updates and reply.
- `project.yml`: DO Functions deployment spec (web action enabled).
- `local_server.py`: FastAPI server for local webhook testing.
- `Dockerfile`: Local dev/testing image. `.env` holds secrets (not committed).

## Build, Test, and Development Commands
- Docker dev: `docker build -t homiai-bot . && docker run --rm -p 8080:8080 --env-file .env homiai-bot`.
- Local (no Docker): `python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt && python local_server.py`.
- Webhook (local): use a tunnel (e.g., `ngrok http 8080`) and set Telegram webhook to `https://<tunnel>/webhook`.
- Use Available MCP tools where helpful.

## Coding Style & Naming Conventions
- Python/PEP 8: 4-space indentation, line length ≤ 100.
- Names: functions/variables `snake_case`; constants `UPPER_SNAKE_CASE`.
- Logging: use `logging`; avoid `print` in runtime paths.

## Testing Guidelines
- Prefer `pytest` for unit tests under `tests/`. Focus on:
- Parsing Telegram updates, OpenAI error handling, and message formatting (mock network calls).
- Manual: send test messages after setting the webhook; verify responses and latency.

## Commit & Pull Request Guidelines
- Commits: imperative mood, concise subject (≤72 chars); include rationale in body.
- PRs: include run steps, webhook URL used, and screenshots of a sample chat; link issues (`Closes #123`).

## Security & Configuration Tips
- Required: `TELEGRAM_BOT_TOKEN`, `OPENAI_API_KEY` (set as DO Function parameters or in `.env`).
- Never commit secrets. Rotate tokens on leak or on contributor turnover.
 - Function is configured as a web action with `web: raw`; always return `200 OK` quickly to satisfy Telegram.

## Architecture Overview
- Flow: Telegram → DO Function (web: raw) → OpenAI Chat Completions → Telegram `sendMessage`.
- Stateless: conversation kept lightweight; use short system prompt for context.
