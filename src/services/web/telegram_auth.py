import hashlib
import hmac
import time
from urllib.parse import parse_qsl, urlencode


class TelegramAuthError(ValueError):
    """Raised when Telegram Web App init data is invalid."""


def validate_login_widget(
    auth_data: str,
    bot_token: str,
    *,
    max_age_seconds: int = 86400,
    now: int | None = None,
) -> dict:
    """Validate Telegram Login Widget data and return the authenticated user."""
    if not auth_data or not bot_token:
        raise TelegramAuthError("Telegram authentication data is required")

    fields = dict(parse_qsl(auth_data, keep_blank_values=True))
    received_hash = fields.pop("hash", None)
    if not received_hash:
        raise TelegramAuthError("Telegram authentication hash is missing")

    data_check_string = "\n".join(
        f"{key}={value}"
        for key, value in sorted(fields.items())
    )
    secret_key = hashlib.sha256(bot_token.encode("utf-8")).digest()
    expected_hash = hmac.new(
        secret_key,
        data_check_string.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(received_hash, expected_hash):
        raise TelegramAuthError("Telegram authentication signature is invalid")

    try:
        auth_date = int(fields["auth_date"])
    except (KeyError, TypeError, ValueError) as exc:
        raise TelegramAuthError("Telegram authentication date is invalid") from exc

    current_time = int(time.time()) if now is None else now
    if auth_date > current_time or current_time - auth_date > max_age_seconds:
        raise TelegramAuthError("Telegram authentication data has expired")

    try:
        user_id = int(fields["id"])
    except (KeyError, TypeError, ValueError) as exc:
        raise TelegramAuthError("Telegram user ID is invalid") from exc
    if user_id <= 0:
        raise TelegramAuthError("Telegram user ID is invalid")
    user = {key: value for key, value in fields.items() if key != "auth_date"}
    user["id"] = user_id
    return user


def build_login_widget_data(fields: dict[str, str], bot_token: str) -> str:
    """Build signed Login Widget data for deterministic unit tests."""
    data_check_string = "\n".join(
        f"{key}={value}"
        for key, value in sorted(fields.items())
    )
    secret_key = hashlib.sha256(bot_token.encode("utf-8")).digest()
    signature = hmac.new(
        secret_key,
        data_check_string.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return urlencode({**fields, "hash": signature})
