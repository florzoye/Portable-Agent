import json
import time
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from loguru import logger


def emit_event(name: str, **fields: Any) -> None:
    safe_fields = {
        key: value
        for key, value in fields.items()
        if key not in {"token", "code", "secret", "password", "message_content"}
    }
    logger.info("event={}", json.dumps(
        {"event": name, **safe_fields},
        default=str,
        sort_keys=True,
    ))


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
