from fastapi import FastAPI
from contextlib import asynccontextmanager
from fastapi.middleware.cors import CORSMiddleware

from data import init
from db.database import global_db_manager

def create_app(
    title: str,
    routers: list,
    port: int = 8000,
) -> FastAPI:

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        init()
        await global_db_manager.setup()
        await global_db_manager.create_tables()
        yield
        await global_db_manager.close()

    app = FastAPI(title=title, lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    for router in routers:
        app.include_router(router)

    @app.get("/health")
    async def health():
        return {"status": "ok", "service": title}

    return app