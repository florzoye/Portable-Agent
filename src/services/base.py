from fastapi import FastAPI, Request
from contextlib import asynccontextmanager
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import os

from data import init
from db.database import global_db_manager

from utils.setup_logger import setup_logging


def _get_cors_origins() -> list[str]:
    from os import environ

    configured = environ.get("CORS_ORIGINS", "http://localhost:8080")
    return [origin.strip() for origin in configured.split(",") if origin.strip()]

def create_app(
    title: str,
    routers: list,
    port: int = 8000,
    internal_auth: bool = False,
    database_bootstrap=None,
) -> FastAPI:

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        setup_logging(title)
        init()
        
        await global_db_manager.setup()
        if database_bootstrap is not None:
            await database_bootstrap()
        yield
        await global_db_manager.close()

    app = FastAPI(title=title, lifespan=lifespan)

    if internal_auth:
        @app.middleware("http")
        async def require_internal_api_key(request: Request, call_next):
            if request.url.path in {"/health", "/calendar/oauth/callback"}:
                return await call_next(request)
            expected = os.environ.get("INTERNAL_API_KEY", "").strip()
            provided = request.headers.get("X-Internal-Api-Key", "")
            if not expected or provided != expected:
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Internal authentication required"},
                )
            return await call_next(request)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=_get_cors_origins(),
        allow_methods=["*"],
        allow_headers=["*"],
    )

    for router in routers:
        app.include_router(router)

    @app.get("/health")
    async def health():
        return {"status": "ok", "service": title}

    return app