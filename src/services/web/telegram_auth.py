import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl, urlencode


class TelegramAuthError(ValueError):
    """Raised when Telegram Web App init data is invalid."""


def validate_init_data(
    init_data: str,
    bot_token: str,
    *,
    max_age_seconds: int = 86400,
    now: int | None = None,
) -> dict:
    """Validate Telegram Web App init data and return the authenticated user."""
    if not init_data or not bot_token:
        raise TelegramAuthError("Telegram init data is required")

    fields = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = fields.pop("hash", None)
    if not received_hash:
        raise TelegramAuthError("Telegram init data hash is missing")

    data_check_string = "\n".join(
        f"{key}={value}"
        for key, value in sorted(fields.items())
    )
    secret_key = hmac.new(
        b"WebAppData",
        bot_token.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    expected_hash = hmac.new(
        secret_key,
        data_check_string.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(received_hash, expected_hash):
        raise TelegramAuthError("Telegram init data signature is invalid")

    try:
        auth_date = int(fields["auth_date"])
    except (KeyError, TypeError, ValueError) as exc:
        raise TelegramAuthError("Telegram auth date is invalid") from exc

    current_time = int(time.time()) if now is None else now
    if auth_date > current_time or current_time - auth_date > max_age_seconds:
        raise TelegramAuthError("Telegram init data has expired")

    try:
        user = json.loads(fields["user"])
    except (KeyError, TypeError, json.JSONDecodeError) as exc:
        raise TelegramAuthError("Telegram user data is invalid") from exc

    if not isinstance(user, dict) or not isinstance(user.get("id"), int):
        raise TelegramAuthError("Telegram user ID is missing")
    return user


def build_init_data(fields: dict[str, str], bot_token: str) -> str:
    """Build signed init data for deterministic unit tests."""
    data_check_string = "\n".join(
        f"{key}={value}"
        for key, value in sorted(fields.items())
    )
    secret_key = hmac.new(
        b"WebAppData",
        bot_token.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    signature = hmac.new(
        secret_key,
        data_check_string.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return urlencode({**fields, "hash": signature})
