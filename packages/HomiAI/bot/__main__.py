import base64
import json
import os
from typing import Dict, Any



def _parse_body(event: Dict[str, Any]) -> Dict[str, Any]:
    # web: parsed ⇒ Telegram JSON merged at top-level
    if isinstance(event, dict) and ("update_id" in event or "message" in event):
        return event
    # web: raw ⇒ body string under http.body
    http = event.get("http") if isinstance(event, dict) else None
    body = None
    if isinstance(http, dict):
        body = http.get("body")
    if body is None:
        # Legacy key fallback
        body = event.get("__ow_body")
    if isinstance(body, (dict, list)):
        return body
    if isinstance(body, str):
        try:
            return json.loads(body)
        except Exception:
            try:
                decoded = base64.b64decode(body)
                return json.loads(decoded)
            except Exception:
                return {}
    return {}


def main(args: Dict[str, Any]):
    # Prefer env; fall back to parameters passed in args
    tg = os.getenv("TELEGRAM_BOT_TOKEN") or args.get("TELEGRAM_BOT_TOKEN")
    oa = os.getenv("OPENAI_API_KEY") or args.get("OPENAI_API_KEY")
    if tg:
        os.environ["TELEGRAM_BOT_TOKEN"] = tg
    if oa:
        os.environ["OPENAI_API_KEY"] = oa

    # Import after setting env so the bot initializes with correct creds
    try:
        from .bot import process_update  # type: ignore
    except ImportError:
        from bot import process_update  # type: ignore

    update = _parse_body(args)
    process_update(update)
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "text/plain"},
        "body": "OK",
    }
