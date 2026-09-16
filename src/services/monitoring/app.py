import os
import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from db.sqlalchemy.monitoring_crud import MonitoringORM


MAX_EVENTS = 1000
_repositories: dict[str, MonitoringORM] = {}


def _repository() -> MonitoringORM:
    path = os.environ.get("MONITORING_DB_PATH", "data/db/monitoring.db")
    if path not in _repositories:
        _repositories[path] = MonitoringORM(
            f"sqlite+aiosqlite:///{path}",
            max_events=MAX_EVENTS,
        )
    return _repositories[path]


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
    repository = _repository()
    await repository.create_tables()
    await repository.record(payload)
    return {"accepted": True}


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/stats")
async def stats(x_monitoring_key: str | None = Header(default=None)):
    _authorized(x_monitoring_key)
    return await _repository().stats()
