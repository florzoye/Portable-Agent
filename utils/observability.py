import json
import asyncio
import os
import secrets
import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from loguru import logger


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
        key: value
        for key, value in fields.items()
        if key not in {"token", "code", "secret", "password", "message_content"}
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
