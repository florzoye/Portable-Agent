import pathlib
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger
from pydantic import BaseModel

from data import get_config
from src.agents.chat import AgentInvoker, StreamSender
from src.agents.llms.initializer import LLMInitializer
from src.agents.tools.calendar import close_calendar_client
from src.agents.tools.reminders import close_reminders_client
from src.factories.checkpointer_factory import close_checkpointer, get_checkpointer
from src.factories.tools_factory import get_tools
from src.services.web.dependencies import get_agent, get_session_model, set_session_model
from utils.renderers import MessageRenderer

STATIC_DIR = pathlib.Path(__file__).parent / "static"


def _model_id(llm) -> str:
    return getattr(llm, "model", None) or getattr(llm, "model_name", None) or type(llm).__name__


def _build_model_list() -> list[dict]:
    wrappers = LLMInitializer.get_wrappers()
    llms = LLMInitializer.get_llms()
    return [
        {"id": _model_id(llm), "label": f"{_model_id(llm)} ({type(w).__name__})"}
        for w, llm in zip(wrappers, llms)
    ]


def _llm_by_id(model_id: str):
    for llm in LLMInitializer.get_llms():
        if _model_id(llm) == model_id:
            return llm
    return None


class WebSocketSender(StreamSender):
    """Delivers streamed tokens to the client over a WebSocket connection."""

    def __init__(self, websocket: WebSocket):
        self.ws = websocket

    async def send_chunk(self, chunk: str) -> None:
        await self.ws.send_json({"type": "chunk", "content": chunk})

    async def send_done(self) -> None:
        await self.ws.send_json({"type": "done"})


@asynccontextmanager
async def lifespan(app: FastAPI):
    await get_tools()
    await LLMInitializer.initialize()
    await get_checkpointer()
    logger.info("🤖 Web assistant started")
    yield
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


@app.get("/models")
async def list_models():
    """Return all available LLM models."""
    return {"models": _build_model_list()}


class SelectModelRequest(BaseModel):
    model_id: str


@app.post("/session/{session_id}/model")
async def select_model(session_id: str, body: SelectModelRequest):
    llm = _llm_by_id(body.model_id)
    if llm is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Model '{body.model_id}' not found")
    set_session_model(session_id, llm)
    return {"session_id": session_id, "active_model": body.model_id}


@app.get("/session/{session_id}/model")
async def current_model(session_id: str):
    llm = get_session_model(session_id)
    return {"session_id": session_id, "active_model": _model_id(llm)}


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
                llm = get_session_model(session_id)

                invoker = AgentInvoker(agent, session_id)
                response = await invoker.invoke(
                    user_message=text,
                    runnable_config=cfg.RUNNABLE_CONFIG,
                    llm=llm,
                    sender=WebSocketSender(websocket),
                )

                html = MessageRenderer.for_web(response)
                await websocket.send_json({"type": "message", "content": html})

            except Exception as e:
                logger.exception(f"Agent error for session={session_id}: {e}")
                await websocket.send_json({
                    "type": "error",
                    "content": "⚠️ An error occurred, please try again",
                })

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected: session={session_id}")