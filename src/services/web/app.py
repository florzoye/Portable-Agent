import asyncio
from loguru import logger
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from src.agents.llms.initializer import LLMInitializer
from src.factories.tools_factory import get_tools
from src.factories.checkpointer_factory import get_checkpointer, close_checkpointer
from src.agents.tools.reminders import close_reminders_client
from src.agents.tools.calendar import close_calendar_client
from src.services.web.dependencies import get_agent
from utils.helpers import _md_to_html
from data import get_config

import pathlib

STATIC_DIR = pathlib.Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await get_tools()
    await LLMInitializer.initialize()
    await get_checkpointer()
    logger.info("🤖 Web assistant started")
    yield
    # Shutdown
    await close_calendar_client()
    await close_reminders_client()
    await close_checkpointer()
    logger.info("🤖 Web assistant stopped")


app = FastAPI(title="AI Assistant", lifespan=lifespan)

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/", response_class=HTMLResponse)
async def index():
    html_file = STATIC_DIR / "index.html"
    return HTMLResponse(content=html_file.read_text(encoding="utf-8"))


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.websocket("/ws/{session_id}")
async def websocket_chat(websocket: WebSocket, session_id: str):
    await websocket.accept()
    cfg = get_config()
    logger.info(f"WebSocket connected: session={session_id}")

    try:
        while True:
            data = await websocket.receive_text()
            text = data.strip()
            if not text:
                continue

            try:
                agent = await get_agent(session_id)
                result = await agent.ainvoke(
                    {"messages": [{"role": "user", "content": text}]},
                    config={
                        "configurable": {"thread_id": session_id},
                        **cfg.RUNNABLE_CONFIG,
                    },
                )
                response = result["messages"][-1].content
                html = _md_to_html(response)
                await websocket.send_json({"type": "message", "content": html})

            except Exception as e:
                logger.exception(f"Agent error for session={session_id}: {e}")
                await websocket.send_json({
                    "type": "error",
                    "content": "⚠️ An error occurred, please try again",
                })

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected: session={session_id}")