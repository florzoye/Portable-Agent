import os
import time
from collections import Counter
from typing import Any

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field


MAX_EVENTS = 1000
EVENTS: list[dict[str, Any]] = []
COUNTERS: Counter[str] = Counter()
TOKENS: Counter[str] = Counter()


class MonitoringEvent(BaseModel):
    event: str = Field(min_length=1, max_length=100)
    model: str | None = Field(default=None, max_length=200)
    user_id: str | None = Field(default=None, max_length=100)
    tool: str | None = Field(default=None, max_length=100)
    status: int | None = None
    duration_ms: float | None = None
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)


app = FastAPI(title="PortableAgent Monitoring")


def _authorized(value: str | None) -> None:
    expected = os.environ.get("MONITORING_API_KEY")
    if expected and value != expected:
        raise HTTPException(status_code=401, detail="Invalid monitoring key")


@app.post("/events")
async def ingest(
    event: MonitoringEvent,
    x_monitoring_key: str | None = Header(default=None),
):
    _authorized(x_monitoring_key)
    payload = event.model_dump()
    payload["timestamp"] = time.time()
    EVENTS.append(payload)
    del EVENTS[:-MAX_EVENTS]
    COUNTERS[event.event] += 1
    if event.model:
        TOKENS[event.model] += event.total_tokens or event.input_tokens + event.output_tokens
    return {"accepted": True}


@app.get("/health")
async def health():
    return {"status": "ok", "events": len(EVENTS)}


@app.get("/stats")
async def stats(x_monitoring_key: str | None = Header(default=None)):
    _authorized(x_monitoring_key)
    return {
        "events": dict(COUNTERS),
        "tokens_by_model": dict(TOKENS),
        "recent_events": EVENTS[-50:],
    }
