# HomiAI Telegram Bot

A conversational Telegram bot backed by OpenAI, deployed on DigitalOcean Functions. Local development runs via a small FastAPI server and Docker.

## Quick Start (Local)
- Prereqs: Python 3.11, [`uv`](https://docs.astral.sh/uv/) (recommended), Docker (optional), `ngrok` (optional for webhook tests).
- Configure env: `cp .env.example .env` and set `TELEGRAM_BOT_TOKEN`, `OPENAI_API_KEY`.
- Option A — uv (recommended):
  - `uv sync`
  - `uv run python local_server.py`
- Option B — Docker (uses uv inside the image):
  - `docker build -t homiai-bot .`
  - `docker run --rm -p 8080:8080 --env-file .env homiai-bot`
- Option C — Virtualenv (fallback):
  - `python -m venv .venv && source .venv/bin/activate`
  - `pip install -r requirements.txt`
  - `python local_server.py`
- Health check: `curl http://localhost:8080/` → `{ "ok": true }`.
- Local webhook (optional): `ngrok http 8080` then
  - `curl -X POST "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/setWebhook" -d url=https://<tunnel>/webhook`

## Project Structure
- `packages/telegram/bot/bot.py`: Processes Telegram updates; calls OpenAI; replies via `sendMessage` (stdlib-only HTTP).
- `packages/telegram/bot/__main__.py`: DigitalOcean Functions web action entrypoint (handles `web: raw`).
- `project.yml`: DO Functions deployment spec (web action, env inputs).
- `local_server.py`: FastAPI app exposing `POST /webhook` for local testing.
- `Dockerfile`, `.dockerignore`: Containerized local dev.
- `AGENTS.md`: Contributor guidelines. `SETUP.md`: DO deployment steps.

## Development Workflow
- Edit logic in `packages/telegram/bot/bot.py`; restart the server/container to apply changes.
- Lint (optional): `uv run ruff check .` (or `pip install ruff && ruff check .`)
- Tests (optional): add `pytest` tests under `tests/` and run `pytest -q`.
- Send yourself Telegram messages to verify responses and latency.

## Deployment (DigitalOcean)
- Install and auth: `doctl auth init` and `doctl serverless install`.
- Set secrets as parameters (or export for YAML substitution):
  - `export TELEGRAM_BOT_TOKEN=... OPENAI_API_KEY=...`
  - or: `doctl serverless functions update telegram/bot --param TELEGRAM_BOT_TOKEN <token> --param OPENAI_API_KEY <key>` after first deploy
- Deploy (with env vars):
  - `cat > .env.serverless <<'EOF'`
  - `TELEGRAM_BOT_TOKEN=123456:YOUR_TOKEN`
  - `OPENAI_API_KEY=sk-...`
  - `EOF`
  - `doctl serverless deploy . --env .env.serverless`
- Get URL: `doctl serverless functions get telegram/bot`
- Set webhook to that URL via Telegram API. See `SETUP.md` for details.

Notes
- The function uses `web: raw` and returns `200 OK` with a simple `OK` body to satisfy Telegram webhook requirements.
- Check webhook health: `curl "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/getWebhookInfo"`.

## Environment
- Required: `TELEGRAM_BOT_TOKEN`, `OPENAI_API_KEY`.
- Never commit secrets; `.env` is git-ignored.

## CI/CD (GitHub Actions)
- Automated deploys on push to `main`/`master` via `.github/workflows/main.yml`.
- Required repository secrets:
  - `DIGITALOCEAN_ACCESS_TOKEN`: Personal access token with Functions access.
  - `DO_FUNCTIONS_NAMESPACE` (optional): Target namespace; if unset, the first available is used.
  - `TELEGRAM_BOT_TOKEN`, `OPENAI_API_KEY`: Used for YAML substitution during deploy.
- The workflow:
  - Installs `doctl` and the DO Serverless plugin.
  - Connects to the namespace and runs `doctl serverless deploy . --env .env.serverless` with secrets populated from GitHub.
  - Fetches the `HomiAI/bot` URL and resets/sets the Telegram webhook to that URL.
  - Verifies activation returns `200`.
