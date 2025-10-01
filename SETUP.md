# DigitalOcean Functions Setup

This guide walks through deploying the Telegram bot as a DigitalOcean Function and wiring the Telegram webhook.

## Prerequisites
- Telegram bot token from @BotFather.
- DigitalOcean account and a project.
- `doctl` installed and authenticated: `doctl auth init`.
- DO Serverless plugin installed: `doctl serverless install`.

## Configure Secrets
- Option A — create an env file for YAML substitution during deploy:
  - `cat > .env.serverless <<'EOF'`
  - `TELEGRAM_BOT_TOKEN=123456:YOUR_TOKEN`
  - `OPENAI_API_KEY=sk-...`
  - `EOF`
  - deploy with `doctl serverless deploy . --env-file .env.serverless`
- Option B — export variables, write them to a temporary file, then deploy:
  - `export TELEGRAM_BOT_TOKEN=123456:YOUR_TOKEN`
  - `export OPENAI_API_KEY=sk-...`
  - `printf "TELEGRAM_BOT_TOKEN=%s\nOPENAI_API_KEY=%s\n" "$TELEGRAM_BOT_TOKEN" "$OPENAI_API_KEY" > /tmp/do.env`
  - `doctl serverless deploy . --env-file /tmp/do.env`
  - `rm /tmp/do.env`
- Option C — set as function parameters after deploy:
  - `doctl serverless functions update telegram/bot --param TELEGRAM_BOT_TOKEN "$TELEGRAM_BOT_TOKEN" --param OPENAI_API_KEY "$OPENAI_API_KEY"`

## Deploy the Function
- Ensure structure is intact: `project.yml` and `packages/telegram/bot/` exist.
- Deploy (supplying env file): `doctl serverless deploy . --env-file .env.serverless`
- Verify: `doctl serverless functions list` and locate `telegram/bot`.

## CI/CD via GitHub Actions
- This repo includes `.github/workflows/main.yml` to auto-deploy on push to `main`/`master`.
- Configure repository secrets:
  - `DIGITALOCEAN_ACCESS_TOKEN`: DO PAT with Functions access.
  - `DO_FUNCTIONS_NAMESPACE` (optional): Specific namespace to target.
  - `TELEGRAM_BOT_TOKEN` and `OPENAI_API_KEY`: Substituted into `project.yml` at deploy time.
- The workflow will:
  - Install `doctl` and the serverless plugin, connect to the namespace.
  - Deploy the function defined in `project.yml`.
  - Fetch the `HomiAI/bot` HTTPS URL and update the Telegram webhook.
  - Perform a simple activation test expecting `200 OK`.

## Get HTTPS URL
- Get route URL: `doctl serverless functions get telegram/bot` (look for Web Action URL) or `doctl serverless routes list`.

## Set Telegram Webhook
- Replace `<URL>` with the function URL:
  - `curl -X POST "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/setWebhook" -d url=<URL>`
- Test: send a message to your bot; you should get a reply.
 - Health check: `curl "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/getWebhookInfo"` — verify no `last_error_message`.

## Local Development with Docker
- Create `.env` from `.env.example` and fill values.
- Build + run: `docker build -t homiai-bot . && docker run --rm -p 8080:8080 --env-file .env homiai-bot`.
- Expose locally (optional): `ngrok http 8080` then set webhook to `https://<tunnel>/webhook`.

## Notes & Troubleshooting
- Logs: check DO activations/logs: `doctl serverless activations list` / `doctl serverless activations get <id>`.
- Timeouts: increase in `project.yml` (`limits.timeout`) if needed.
- Secrets: rotate tokens on leak; redeploy via `doctl serverless deploy . --env-file .env.serverless` after changing env.
- Validation: Telegram requires HTTPS and a reachable webhook URL.
 - Webhook mode: project uses `web: raw`; function returns `200 OK` and body `OK`.
