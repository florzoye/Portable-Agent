import pathlib
import asyncio
import os
import secrets
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Request, Response, Cookie
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
from src.services.dependencies import (
    clear_session_model,
    get_agent,
    get_session_model,
    set_session_model,
)
from utils.renderers import MessageRenderer
from src.services.web.one_time_code import normalize_login_code

STATIC_DIR = pathlib.Path(__file__).parent / "static"
SESSION_COOKIE = "portable_session"
SESSION_TTL = 86400
SESSION_KEY_PREFIX = "web_session:"
SESSION_THREAD_PREFIX = "web_session_thread:"


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

async def _redis_listener(session_id: str, websocket: WebSocket):
    cfg = get_config()
    pubsub = cfg.redis_client.pubsub()
    await pubsub.subscribe(f"ws_push:{session_id}")
    try:
        async for message in pubsub.listen():
            if message["type"] != "message":
                continue
            await websocket.send_text(message["data"])  
    except asyncio.CancelledError:
        pass
    finally:
        await pubsub.unsubscribe(f"ws_push:{session_id}")
        await pubsub.aclose()

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

class CodeLoginRequest(BaseModel):
    code: str


async def _get_session_context(session_id: str | None) -> tuple[int, str]:
    if not session_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    redis = get_config().redis_client
    user_id = await redis.get(f"{SESSION_KEY_PREFIX}{session_id}")
    thread_id = await redis.get(f"{SESSION_THREAD_PREFIX}{session_id}")
    if user_id is None or thread_id is None:
        raise HTTPException(status_code=401, detail="Session expired")
    await redis.expire(f"{SESSION_KEY_PREFIX}{session_id}", SESSION_TTL)
    await redis.expire(f"{SESSION_THREAD_PREFIX}{session_id}", SESSION_TTL)
    return int(user_id), thread_id


@app.post("/auth/code")
async def code_login(body: CodeLoginRequest, response: Response):
    cfg = get_config()
    try:
        code = normalize_login_code(body.code)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc

    user_id = await cfg.redis_client.getdel(f"web_login_code:{code}")
    if user_id is None:
        raise HTTPException(status_code=401, detail="Invalid or expired login code")

    session_id = secrets.token_urlsafe(32)
    thread_id = secrets.token_urlsafe(24)
    await cfg.redis_client.setex(
        f"{SESSION_KEY_PREFIX}{session_id}",
        SESSION_TTL,
        str(user_id),
    )
    await cfg.redis_client.setex(
        f"{SESSION_THREAD_PREFIX}{session_id}",
        SESSION_TTL,
        thread_id,
    )
    response.set_cookie(
        SESSION_COOKIE,
        session_id,
        max_age=SESSION_TTL,
        httponly=True,
        secure=os.environ.get("WEB_COOKIE_SECURE", "false").lower() == "true",
        samesite="lax",
    )
    return {"user_id": int(user_id)}


@app.post("/auth/logout")
async def logout(
    response: Response,
    portable_session: str | None = Cookie(default=None),
):
    user_id, thread_id = await _get_session_context(portable_session)
    redis = get_config().redis_client
    await redis.delete(
        f"{SESSION_KEY_PREFIX}{portable_session}",
        f"{SESSION_THREAD_PREFIX}{portable_session}",
    )
    clear_session_model(thread_id)
    response.delete_cookie(SESSION_COOKIE)
    return {"logged_out": True, "user_id": user_id}


@app.post("/session/{session_id}/model")
async def select_model(
    session_id: str,
    body: SelectModelRequest,
    portable_session: str | None = Cookie(default=None),
):
    user_id, thread_id = await _get_session_context(portable_session)
    llm = _llm_by_id(body.model_id)
    if llm is None:
        
        raise HTTPException(status_code=404, detail=f"Model '{body.model_id}' not found")
    set_session_model(thread_id, llm, user_id)
    return {"session_id": thread_id, "active_model": body.model_id}


@app.get("/session/{session_id}/model")
async def current_model(
    session_id: str,
    portable_session: str | None = Cookie(default=None),
):
    _, thread_id = await _get_session_context(portable_session)
    llm = get_session_model(thread_id)
    return {"session_id": thread_id, "active_model": _model_id(llm)}


@app.websocket("/ws/{session_id}")
async def websocket_chat(websocket: WebSocket, session_id: str):
    portable_session = websocket.cookies.get(SESSION_COOKIE)
    try:
        user_id, thread_id = await _get_session_context(portable_session)
    except HTTPException:
        await websocket.close(code=1008, reason="Authentication required")
        return
    await websocket.accept()
    cfg = get_config()
    logger.info(f"WebSocket connected: session={thread_id}")

    listener_task = asyncio.create_task(_redis_listener(thread_id, websocket))

    try:
        while True:
            data = await websocket.receive_text()
            text = data.strip()
            if not text:
                continue

            try:
                agent = await get_agent(thread_id, user_id)
                llm = get_session_model(thread_id)

                invoker = AgentInvoker(agent, thread_id)
                response = await invoker.invoke(
                    user_message=text,
                    runnable_config=cfg.RUNNABLE_CONFIG,
                    llm=llm,
                    sender=WebSocketSender(websocket),
                )

                html = MessageRenderer.for_web(response)
                await websocket.send_json({"type": "message", "content": html})

            except Exception as e:
                logger.exception(f"Agent error for session={thread_id}: {e}")
                await websocket.send_json({
                    "type": "error",
                    "content": "⚠️ An error occurred, please try again",
                })

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected: session={session_id}")
    finally:
        listener_task.cancel()