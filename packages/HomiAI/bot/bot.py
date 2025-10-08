import os
import logging
import json
import sys
from typing import Any, Dict, Optional, Tuple
from urllib import request, error


logger = logging.getLogger("telegram_bot")
logger.setLevel(logging.INFO)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)],
    force=True,
)


def _get_openai_api_key() -> Optional[str]:
    return os.getenv("OPENAI_API_KEY")


def _get_telegram_bot_token() -> Optional[str]:
    return os.getenv("TELEGRAM_BOT_TOKEN")


OPENAI_API_KEY = _get_openai_api_key()
TELEGRAM_BOT_TOKEN = _get_telegram_bot_token()
PRIMARY_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
FALLBACK_MODEL = os.getenv("OPENAI_FALLBACK_MODEL", "gpt-4o-mini")
OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
OPENAI_CHAT_URL = "https://api.openai.com/v1/chat/completions"
MAX_REPLY_LEN = 4000
FALLBACK_REPLY = "Sorry, I couldn’t think of a good answer just now."


if not TELEGRAM_BOT_TOKEN:
    logger.warning("TELEGRAM_BOT_TOKEN is not set; replies will fail.")
if not OPENAI_API_KEY:
    logger.warning("OPENAI_API_KEY is not set; generation will fail.")


SYSTEM_PROMPT = (
    "You are HomiAI, a concise, friendly assistant. "
    "Answer clearly and helpfully. If you need more context, ask a short follow-up."
)


def _normalize_headers(raw_headers: Any) -> Dict[str, str]:
    if not raw_headers:
        return {}
    try:
        return {str(k).lower(): str(v) for k, v in raw_headers.items()}
    except AttributeError:
        return {}


def _safe_json_loads(body: str) -> Dict[str, Any]:
    if not body:
        return {}
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        return {}


def _post_json(
    url: str,
    payload: Dict[str, Any],
    headers: Optional[Dict[str, str]] = None,
    timeout: int = 20,
) -> Tuple[int, str, Dict[str, str]]:
    data = json.dumps(payload).encode("utf-8")
    req = request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    for key, value in (headers or {}).items():
        req.add_header(key, value)
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            status = resp.getcode()
            body = resp.read().decode("utf-8", errors="replace")
            return status, body, _normalize_headers(resp.headers)
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace") if hasattr(exc, "read") else str(exc)
        return exc.code or 500, body, _normalize_headers(getattr(exc, "headers", None))
    except Exception as exc:  # pragma: no cover - unexpected networking errors
        return 500, str(exc), {}


def _format_usage(usage: Dict[str, Any]) -> str:
    if not usage:
        return "{}"
    mapped = []
    for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
        if key in usage:
            mapped.append(f"{key}={usage[key]}")
    return ", ".join(mapped) or "{}"


def _extract_responses_content(data: Dict[str, Any]) -> str:
    content = data.get("output_text") or ""
    if content:
        return content
    for item in data.get("output", []) or []:
        if item.get("type") != "message":
            continue
        segments = item.get("content") or []
        text_parts = [
            segment.get("text")
            for segment in segments
            if isinstance(segment, dict)
            and segment.get("type") in {"text", "output_text"}
            and segment.get("text")
        ]
        if text_parts:
            return "".join(text_parts)
    return ""


def _extract_openai_error(body: str) -> Dict[str, Any]:
    data = _safe_json_loads(body)
    error_obj = data.get("error") if isinstance(data, dict) else None
    if isinstance(error_obj, dict):
        return {
            "code": error_obj.get("code") or error_obj.get("type"),
            "message": error_obj.get("message"),
            "param": error_obj.get("param"),
            "type": error_obj.get("type"),
        }
    return {"message": body[:200]}


def _should_try_chat_fallback(status: int, error: Dict[str, Any]) -> bool:
    if status in {400, 401, 403, 404, 409, 422, 429}:
        return True
    message = (error.get("message") or "").lower()
    code = (error.get("code") or "").lower()
    triggers = (
        "model_not_found",
        "unsupported_model",
        "invalid_request_error",
        "rate_limit",
        "insufficient_quota",
        "server_error",
        "timeout",
    )
    if any(token in code for token in triggers):
        return True
    patterns = (
        "does not exist",
        "is not available",
        "unrecognized request argument supplied: input",
        "rate limit",
        "quota",
        "timeout",
        "temporarily unavailable",
        "overloaded",
    )
    if any(pattern in message for pattern in patterns):
        return True
    return status >= 500


def _call_openai_responses(api_key: str, user_text: str) -> Tuple[Optional[str], Dict[str, Any]]:
    payload = {
        "model": PRIMARY_MODEL,
        "input": [
            {
                "role": "system",
                "content": [{"type": "text", "text": SYSTEM_PROMPT}],
            },
            {
                "role": "user",
                "content": [{"type": "text", "text": user_text}],
            },
        ],
        "temperature": 0.4,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "OpenAI-Beta": "responses=v1",
    }
    status, body, resp_headers = _post_json(OPENAI_RESPONSES_URL, payload, headers=headers)
    request_id = resp_headers.get("x-request-id") or resp_headers.get("x-openai-request-id")
    meta: Dict[str, Any] = {
        "status": status,
        "body": body,
        "headers": resp_headers,
        "request_id": request_id,
    }
    if status >= 300:
        error_info = _extract_openai_error(body)
        meta["error"] = error_info
        logger.error(
            "OpenAI responses error status=%s request_id=%s code=%s message=%s",
            status,
            request_id,
            error_info.get("code"),
            error_info.get("message") or body[:200],
        )
        return None, meta
    data = _safe_json_loads(body)
    meta["data"] = data
    logger.info(
        "OpenAI responses ok status=%s request_id=%s usage=%s",
        status,
        request_id,
        _format_usage(data.get("usage", {})) if isinstance(data, dict) else "{}",
    )
    content = _extract_responses_content(data if isinstance(data, dict) else {})
    if not content:
        logger.warning(
            "OpenAI responses empty completion status=%s request_id=%s",
            status,
            request_id,
        )
    return (content or None), meta


def _call_openai_chat(api_key: str, user_text: str) -> Tuple[Optional[str], Dict[str, Any]]:
    payload = {
        "model": FALLBACK_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_text},
        ],
        "temperature": 0.4,
    }
    headers = {"Authorization": f"Bearer {api_key}"}
    status, body, resp_headers = _post_json(OPENAI_CHAT_URL, payload, headers=headers)
    request_id = resp_headers.get("x-request-id") or resp_headers.get("x-openai-request-id")
    meta: Dict[str, Any] = {
        "status": status,
        "body": body,
        "headers": resp_headers,
        "request_id": request_id,
    }
    if status >= 300:
        error_info = _extract_openai_error(body)
        meta["error"] = error_info
        logger.error(
            "OpenAI chat completions error status=%s request_id=%s code=%s message=%s",
            status,
            request_id,
            error_info.get("code"),
            error_info.get("message") or body[:200],
        )
        return None, meta
    data = _safe_json_loads(body)
    meta["data"] = data
    logger.info(
        "OpenAI chat completions ok status=%s request_id=%s usage=%s",
        status,
        request_id,
        _format_usage((data or {}).get("usage", {})) if isinstance(data, dict) else "{}",
    )
    choices = (data or {}).get("choices") if isinstance(data, dict) else None
    if not choices:
        logger.warning(
            "OpenAI chat completions empty choices status=%s request_id=%s",
            status,
            request_id,
        )
        return None, meta
    message = choices[0].get("message") if isinstance(choices[0], dict) else {}
    content = message.get("content") if isinstance(message, dict) else None
    return (content or None), meta


def _send_telegram_message(chat_id: int, text: str) -> None:
    token = _get_telegram_bot_token()
    if not token:
        logger.error("Missing TELEGRAM_BOT_TOKEN; cannot send message.")
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    status, body, _ = _post_json(url, payload)
    if status >= 300:
        logger.error("Telegram sendMessage failed status=%s body=%s", status, body[:200])
        return
    data = _safe_json_loads(body)
    if not isinstance(data, dict):
        logger.error("Telegram sendMessage malformed response status=%s body=%s", status, body[:200])
        return
    if not data.get("ok", False):
        logger.error(
            "Telegram sendMessage rejected status=%s error_code=%s description=%s",
            status,
            data.get("error_code"),
            data.get("description"),
        )
        return
    result = data.get("result")
    message_id = result.get("message_id") if isinstance(result, dict) else None
    logger.info("Telegram sendMessage ok status=%s message_id=%s", status, message_id)


def _generate_reply(user_text: str) -> str:
    api_key = _get_openai_api_key()
    if not api_key:
        return "I’m not configured yet. Please try again later."
    try:
        content, meta = _call_openai_responses(api_key, user_text)
        if content:
            return content[:MAX_REPLY_LEN]
        status = meta.get("status", 500)
        error_info = meta.get("error") or {}
        if status < 300:
            logger.info(
                "OpenAI responses returned no content; attempting chat fallback request_id=%s",
                meta.get("request_id"),
            )
            fallback_content, fallback_meta = _call_openai_chat(api_key, user_text)
            if fallback_content:
                return fallback_content[:MAX_REPLY_LEN]
            logger.error(
                "Chat fallback empty response status=%s request_id=%s",
                fallback_meta.get("status"),
                fallback_meta.get("request_id"),
            )
            return FALLBACK_REPLY
        if _should_try_chat_fallback(status, error_info):
            logger.info(
                "Falling back to chat completions model=%s after responses error status=%s code=%s",
                FALLBACK_MODEL,
                status,
                error_info.get("code"),
            )
            fallback_content, fallback_meta = _call_openai_chat(api_key, user_text)
            if fallback_content:
                return fallback_content[:MAX_REPLY_LEN]
            logger.error(
                "Fallback chat completions failed status=%s request_id=%s",
                fallback_meta.get("status"),
                fallback_meta.get("request_id"),
            )
            return FALLBACK_REPLY
        body_snippet = (error_info.get("message") or meta.get("body") or "")[:200]
        logger.error(
            "OpenAI responses rejected request without fallback status=%s code=%s message=%s",
            status,
            error_info.get("code"),
            body_snippet,
        )
        return FALLBACK_REPLY
    except Exception as exc:  # pragma: no cover - defensive guard
        logger.exception("OpenAI generation failed: %s", exc)
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
            logger.info("Unsupported update (no chat_id or text). update_id=%s", update.get("update_id"))
            return
        logger.info(
            "Processing update update_id=%s chat_id=%s text_preview=%r",
            update.get("update_id"),
            chat_id,
            text[:80],
        )
        reply = _generate_reply(text)
        _send_telegram_message(chat_id, reply)
    except Exception:  # pragma: no cover - defensive guard
        logger.exception("Failed to process update")
