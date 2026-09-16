import os
import json
import sqlite3
import time
from pathlib import Path
from collections import Counter
from typing import Any

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field


MAX_EVENTS = 1000
EVENTS: list[dict[str, Any]] = []
COUNTERS: Counter[str] = Counter()
TOKENS: Counter[str] = Counter()


def _database_path() -> str | None:
    value = os.environ.get("MONITORING_DB_PATH", "").strip()
    return value or None


def _init_database() -> None:
    path = _database_path()
    if not path:
        return
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS monitoring_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event TEXT NOT NULL,
                payload TEXT NOT NULL,
                created_at REAL NOT NULL
            )
            """
        )
        connection.commit()


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
_DASHBOARD_PATH = Path(__file__).with_name("dashboard.html")


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    with _DASHBOARD_PATH.open(encoding="utf-8") as dashboard_file:
        return HTMLResponse(dashboard_file.read())


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
    path = _database_path()
    if path:
        _init_database()
        with sqlite3.connect(path) as connection:
            connection.execute(
                "INSERT INTO monitoring_events (event, payload, created_at) VALUES (?, ?, ?)",
                (event.event, json.dumps(payload, default=str), payload["timestamp"]),
            )
            connection.commit()
    return {"accepted": True}


@app.get("/health")
async def health():
    return {"status": "ok", "events": len(EVENTS)}


@app.get("/stats")
async def stats(x_monitoring_key: str | None = Header(default=None)):
    _authorized(x_monitoring_key)
    path = _database_path()
    if path:
        _init_database()
        with sqlite3.connect(path) as connection:
            rows = connection.execute(
                "SELECT payload FROM monitoring_events ORDER BY id DESC LIMIT 50"
            ).fetchall()
            events = connection.execute(
                "SELECT event, COUNT(*) FROM monitoring_events GROUP BY event"
            ).fetchall()
            tokens = connection.execute(
                """
                SELECT json_extract(payload, '$.model'),
                       SUM(COALESCE(json_extract(payload, '$.total_tokens'), 0))
                FROM monitoring_events
                WHERE json_extract(payload, '$.model') IS NOT NULL
                GROUP BY json_extract(payload, '$.model')
                """
            ).fetchall()
        return {
            "events": dict(events),
            "tokens_by_model": {model: int(total or 0) for model, total in tokens},
            "recent_events": [json.loads(payload) for (payload,) in reversed(rows)],
        }
    return {
        "events": dict(COUNTERS),
        "tokens_by_model": dict(TOKENS),
        "recent_events": EVENTS[-50:],
    }
