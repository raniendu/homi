import os
import logging
import json
from typing import Dict, Any
from urllib import request, error


logger = logging.getLogger("telegram_bot")
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')


OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

if not TELEGRAM_BOT_TOKEN:
    logger.warning("TELEGRAM_BOT_TOKEN is not set; replies will fail.")
if not OPENAI_API_KEY:
    logger.warning("OPENAI_API_KEY is not set; generation will fail.")


SYSTEM_PROMPT = (
    "You are HomiAI, a concise, friendly assistant. "
    "Answer clearly and helpfully. If you need more context, ask a short follow-up."
)


def _post_json(url: str, payload: Dict[str, Any], headers: Dict[str, str] | None = None, timeout: int = 20) -> tuple[int, str]:
    data = json.dumps(payload).encode("utf-8")
    req = request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            status = resp.getcode()
            body = resp.read().decode("utf-8", errors="replace")
            return status, body
    except error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace") if hasattr(e, "read") else str(e)
        return e.code or 500, body
    except Exception as e:
        return 500, str(e)


def _send_telegram_message(chat_id: int, text: str) -> None:
    if not TELEGRAM_BOT_TOKEN:
        logger.error("Missing TELEGRAM_BOT_TOKEN; cannot send message.")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    status, body = _post_json(url, payload)
    if status >= 300:
        logger.error("Telegram sendMessage failed: %s %s", status, body)
    else:
        logger.info("Telegram sendMessage ok: %s", status)


def _generate_reply(user_text: str) -> str:
    if not OPENAI_API_KEY:
        return "I’m not configured yet. Please try again later."
    try:
        url = "https://api.openai.com/v1/chat/completions"
        payload = {
            "model": "gpt-4o-mini",
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_text},
            ],
            "temperature": 0.4,
        }
        headers = {"Authorization": f"Bearer {OPENAI_API_KEY}"}
        status, body = _post_json(url, payload, headers=headers)
        logger.info("OpenAI chat status=%s", status)
        if status >= 300:
            logger.error("OpenAI API error: %s %s", status, body)
            return "Sorry, I couldn’t think of a good answer just now."
        data = json.loads(body)
        content = data.get("choices", [{}])[0].get("message", {}).get("content") or ""
        return (content or "")[:4000] or "(no content)"
    except Exception as e:
        logger.exception("OpenAI generation failed: %s", e)
        return "Sorry, I hit an error while thinking about that."


def process_update(update: Dict[str, Any]) -> None:
    """Process a Telegram update and send a reply."""
    try:
        message = update.get("message") or update.get("edited_message")
        if not message:
            logger.info("No message in update; ignoring.")
            return
        chat = message.get("chat", {})
        chat_id = chat.get("id")
        text = message.get("text") or message.get("caption")
        if not chat_id or not isinstance(text, str):
            logger.info("Unsupported update (no chat_id or text).")
            return
        logger.info("Processing update chat_id=%s text_preview=%r", chat_id, text[:80])
        reply = _generate_reply(text)
        _send_telegram_message(chat_id, reply)
    except Exception:
        logger.exception("Failed to process update")
