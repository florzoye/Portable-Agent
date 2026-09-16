import json
import asyncio
import os
import secrets
import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from loguru import logger


_SENSITIVE_FIELD_PARTS = ("api_key", "token", "secret", "password", "authorization")


def _is_sensitive_field(name: str) -> bool:
    normalized = name.lower().replace("-", "_")
    return any(part in normalized for part in _SENSITIVE_FIELD_PARTS)


def _safe_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: "[REDACTED]" if _is_sensitive_field(str(key)) else _safe_value(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_safe_value(item) for item in value]
    return value


def _monitoring_url() -> str | None:
    value = os.environ.get("MONITORING_URL", "").strip()
    return value.rstrip("/") if value else None


async def _send_to_monitoring(payload: dict[str, Any]) -> None:
    url = _monitoring_url()
    if not url:
        return
    import aiohttp

    try:
        timeout = aiohttp.ClientTimeout(total=1)
        headers = {}
        api_key = os.environ.get("MONITORING_API_KEY", "").strip()
        if api_key:
            headers["X-Monitoring-Key"] = api_key
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(f"{url}/events", json=payload, headers=headers):
                return
    except (aiohttp.ClientError, asyncio.TimeoutError, OSError):
        logger.debug("Monitoring service is unavailable")


def emit_event(name: str, **fields: Any) -> None:
    safe_fields = {
        key: "[REDACTED]" if _is_sensitive_field(key) else _safe_value(value)
        for key, value in fields.items()
        if key not in {
            "code",
            "message_content",
            "password",
            "secret",
            "token",
        }
    }
    payload = {
        "event": name,
        "event_id": secrets.token_hex(8),
        **safe_fields,
    }
    logger.info("event={}", json.dumps(
        payload,
        default=str,
        sort_keys=True,
    ))
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    loop.create_task(_send_to_monitoring(payload))


@contextmanager
def timed_event(name: str, **fields: Any) -> Iterator[None]:
    started = time.perf_counter()
    try:
        yield
    except Exception:
        emit_event(
            f"{name}.failed",
            duration_ms=round((time.perf_counter() - started) * 1000, 2),
            **fields,
        )
        raise
    else:
        emit_event(
            f"{name}.completed",
            duration_ms=round((time.perf_counter() - started) * 1000, 2),
            **fields,
        )
