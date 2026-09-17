import os
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from db.monitoring_protocol import MonitoringBase
from src.services.monitoring.composition import get_legacy_repository


_DASHBOARD_PATH = Path(__file__).with_name("dashboard.html")


class MonitoringEvent(BaseModel):
    event: str = Field(min_length=1, max_length=100)
    model: str | None = Field(default=None, max_length=200)
    user_id: str | int | None = Field(default=None)
    tool: str | None = Field(default=None, max_length=100)
    status: int | None = None
    duration_ms: float | None = None
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)


def _authorized(value: str | None) -> None:
    expected = os.environ.get("MONITORING_API_KEY", "").strip()
    if not expected:
        raise HTTPException(
            status_code=503,
            detail="Monitoring API authentication is not configured",
        )
    if value != expected:
        raise HTTPException(status_code=401, detail="Invalid monitoring key")


def create_app(repository: MonitoringBase) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await repository.create_tables()
        yield
        close = getattr(repository, "close", None)
        if close is not None:
            await close()

    app = FastAPI(title="PortableAgent Monitoring", lifespan=lifespan)

    @app.get("/dashboard", response_class=HTMLResponse)
    async def dashboard():
        with _DASHBOARD_PATH.open(encoding="utf-8") as dashboard_file:
            return HTMLResponse(dashboard_file.read())

    @app.post("/events")
    async def ingest(
        event: MonitoringEvent,
        x_monitoring_key: str | None = Header(default=None),
    ):
        _authorized(x_monitoring_key)
        payload = event.model_dump()
        payload["timestamp"] = time.time()
        await repository.record(payload)
        return {"accepted": True}

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.get("/stats")
    async def stats(x_monitoring_key: str | None = Header(default=None)):
        _authorized(x_monitoring_key)
        return await repository.stats()

    return app


async def ingest(
    event: MonitoringEvent,
    x_monitoring_key: str | None = None,
):
    """Compatibility entrypoint for in-process monitoring callers."""
    _authorized(x_monitoring_key)
    repository = get_legacy_repository()
    await repository.create_tables()
    payload = event.model_dump()
    payload["timestamp"] = time.time()
    await repository.record(payload)
    return {"accepted": True}


async def stats(x_monitoring_key: str | None = None):
    _authorized(x_monitoring_key)
    return await get_legacy_repository().stats()


async def dashboard():
    with _DASHBOARD_PATH.open(encoding="utf-8") as dashboard_file:
        return HTMLResponse(dashboard_file.read())
