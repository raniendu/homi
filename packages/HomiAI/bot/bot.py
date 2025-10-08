import os
import logging
import json
import sys
from typing import Any, Dict, Optional, Tuple
from urllib import request, error

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover - library may be missing in some environments
    OpenAI = None  # type: ignore[assignment]


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


def _create_openai_client(api_key: str):
    if OpenAI is not None:
        try:
            return OpenAI(api_key=api_key)
        except TypeError:
            logger.info("OpenAI client class rejected api_key argument; falling back to legacy module usage.")
        except Exception:
            raise
    try:
        import openai as openai_module  # type: ignore
    except ImportError as exc:  # pragma: no cover - should be prevented by dependency installation
        raise RuntimeError("openai package is not installed") from exc
    openai_module.api_key = api_key  # type: ignore[attr-defined]
    return openai_module


def _object_to_dict(payload: Any) -> Dict[str, Any]:
    if payload is None:
        return {}
    if isinstance(payload, dict):
        return payload
    for attr in ("model_dump", "to_dict", "dict"):
        method = getattr(payload, attr, None)
        if callable(method):
            try:
                data = method()
                if isinstance(data, dict):
                    return data
            except Exception:
                continue
    return {}


def _usage_to_dict(usage: Any) -> Dict[str, Any]:
    if usage is None:
        return {}
    if isinstance(usage, dict):
        return usage
    return _object_to_dict(usage)


def _extract_openai_exception(exc: Exception) -> Tuple[Optional[int], Dict[str, Any]]:
    status = getattr(exc, "status_code", None)
    code = getattr(exc, "code", None)
    message = getattr(exc, "message", None)
    response_payload: Dict[str, Any] = {}
    response = getattr(exc, "response", None)
    if response is not None:
        try:
            response_payload = response.json()  # type: ignore[attr-defined]
        except Exception:
            response_payload = {}
    elif hasattr(exc, "body"):
        try:
            response_payload = json.loads(getattr(exc, "body"))
        except Exception:
            response_payload = {}
    error_obj = response_payload.get("error") if isinstance(response_payload, dict) else None
    if isinstance(error_obj, dict):
        code = code or error_obj.get("code") or error_obj.get("type")
        message = message or error_obj.get("message")
    clean_message = message or str(exc)
    return status, {"code": code, "message": clean_message}


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


def _should_try_chat_fallback(status: Optional[int], error: Dict[str, Any]) -> bool:
    if status is None:
        return True
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


def _call_openai_responses(client, user_text: str) -> Optional[str]:
    responses_api = getattr(client, "responses", None)
    create_fn = getattr(responses_api, "create", None) if responses_api else None
    if not callable(create_fn):
        logger.info("OpenAI responses API not available; skipping primary completion path.")
        return None
    response = create_fn(
        model=PRIMARY_MODEL,
        input=[
            {
                "role": "system",
                "content": [{"type": "text", "text": SYSTEM_PROMPT}],
            },
            {
                "role": "user",
                "content": [{"type": "text", "text": user_text}],
            },
        ],
        temperature=0.4,
    )
    request_id = getattr(response, "id", None)
    usage = _format_usage(_usage_to_dict(getattr(response, "usage", None)))
    logger.info(
        "OpenAI responses ok request_id=%s usage=%s",
        request_id,
        usage or "{}",
    )
    content = getattr(response, "output_text", None)
    if content:
        return content
    response_dict = _object_to_dict(response)
    content = _extract_responses_content(response_dict)
    if not content:
        logger.warning(
            "OpenAI responses empty completion request_id=%s",
            request_id,
        )
    return content or None


def _call_openai_chat(client, user_text: str) -> Optional[str]:
    chat_namespace = getattr(client, "chat", None)
    completions_namespace = getattr(chat_namespace, "completions", None) if chat_namespace else None
    create_fn = getattr(completions_namespace, "create", None) if completions_namespace else None
    legacy_chat_completion = getattr(client, "ChatCompletion", None)

    if callable(create_fn):
        response = create_fn(
            model=FALLBACK_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_text},
            ],
            temperature=0.4,
        )
        request_id = getattr(response, "id", None)
        usage = _format_usage(_usage_to_dict(getattr(response, "usage", None)))
        logger.info(
            "OpenAI chat completions ok request_id=%s usage=%s",
            request_id,
            usage or "{}",
        )
        choices = getattr(response, "choices", None)
        if not choices:
            logger.warning(
                "OpenAI chat completions empty choices request_id=%s",
                request_id,
            )
            return None
        first = choices[0]
        message = getattr(first, "message", None)
        if isinstance(message, dict):
            content = message.get("content")
        else:
            content = getattr(message, "content", None)
        return content or None

    if legacy_chat_completion and hasattr(legacy_chat_completion, "create"):
        response = legacy_chat_completion.create(  # type: ignore[call-arg]
            model=FALLBACK_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_text},
            ],
            temperature=0.4,
        )
        if isinstance(response, dict):
            usage = _format_usage(response.get("usage", {}))
            logger.info("OpenAI ChatCompletion ok usage=%s", usage or "{}")
            choices = response.get("choices") or []
            if not choices:
                logger.warning("OpenAI ChatCompletion returned no choices.")
                return None
            message = choices[0].get("message") if isinstance(choices[0], dict) else None
            if isinstance(message, dict):
                return message.get("content") or None
            return None
        return None

    raise RuntimeError("OpenAI chat completions API is unavailable in this client")


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
        client = _create_openai_client(api_key)
    except RuntimeError as exc:
        logger.error("OpenAI client initialization failed: %s", exc)
        return "I’m not configured yet. Please try again later."
    except Exception as exc:  # pragma: no cover - defensive guard
        logger.exception("OpenAI client initialization crashed: %s", exc)
        return "Sorry, I hit an error while thinking about that."

    should_fallback = False
    try:
        content = _call_openai_responses(client, user_text)
        if content:
            return content[:MAX_REPLY_LEN]
        logger.info("OpenAI responses returned no content; attempting chat fallback")
        should_fallback = True
    except Exception as exc:
        status, error_info = _extract_openai_exception(exc)
        logger.error(
            "OpenAI responses error status=%s code=%s message=%s",
            status,
            error_info.get("code"),
            error_info.get("message"),
        )
        should_fallback = _should_try_chat_fallback(status, error_info)
        if not should_fallback:
            return FALLBACK_REPLY
    try:
        if not should_fallback:
            return FALLBACK_REPLY
        fallback_content = _call_openai_chat(client, user_text)
        if fallback_content:
            return fallback_content[:MAX_REPLY_LEN]
        logger.error("Chat fallback empty response")
        return FALLBACK_REPLY
    except Exception as exc:
        status, error_info = _extract_openai_exception(exc)
        logger.error(
            "Fallback chat completions error status=%s code=%s message=%s",
            status,
            error_info.get("code"),
            error_info.get("message"),
        )
        return FALLBACK_REPLY
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
