import pathlib
import asyncio
import os
import secrets
import time
from collections import deque
from contextlib import asynccontextmanager
from contextlib import suppress

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
    get_user_model,
    set_session_model,
)
from utils.renderers import MessageRenderer
from src.services.web.one_time_code import (
    LOGIN_ATTEMPT_LIMIT,
    LOGIN_ATTEMPT_WINDOW,
    login_attempt_key,
    login_code_key,
    normalize_login_code,
)
from utils.observability import emit_event
from src.services.dependencies import get_model_profiles
from src.services.models.providers import ModelProvider
from src.agents.providers.base import ProviderConfigurationError
from src.agents.providers.base import provider_user_message

STATIC_DIR = pathlib.Path(__file__).parent / "static"
SESSION_COOKIE = "portable_session"
SESSION_TTL = 86400
SESSION_KEY_PREFIX = "web_session:"
SESSION_THREAD_PREFIX = "web_session_thread:"
MAX_WEBSOCKET_MESSAGE_SIZE = 4000
AGENT_INVOKE_TIMEOUT = 120
WEBSOCKET_RATE_WINDOW = 60
WEBSOCKET_RATE_LIMIT = 30
PROVIDER_DIAGNOSTIC_COOLDOWN = 30
_THREAD_LOCKS: dict[str, asyncio.Lock] = {}
_THREAD_MESSAGE_TIMES: dict[str, deque[float]] = {}


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


async def _acquire_provider_diagnostic_slot(user_id: int, profile_id: int) -> bool:
    key = f"provider_diagnostic:{user_id}:{profile_id}"
    return bool(
        await get_config().redis_client.set(
            key,
            "1",
            ex=PROVIDER_DIAGNOSTIC_COOLDOWN,
            nx=True,
        )
    )

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


class CreateModelProfileRequest(BaseModel):
    provider: ModelProvider
    model_name: str
    display_name: str = ""
    api_key: str | None = None


@app.get("/model-profiles")
async def list_model_profiles(
    portable_session: str | None = Cookie(default=None),
):
    user_id, _ = await _get_session_context(portable_session)
    profiles = await get_model_profiles().list(user_id)
    return {
        "profiles": [
            {
                "id": profile.id,
                "provider": profile.provider.value,
                "model_name": profile.model_name,
                "display_name": profile.display_name,
                "is_active": profile.is_active,
            }
            for profile in profiles
        ]
    }


@app.get("/model-providers")
async def list_model_providers(
    portable_session: str | None = Cookie(default=None),
):
    await _get_session_context(portable_session)
    return {
        "providers": [
            {
                "id": capability.provider.value,
                "name": capability.display_name,
                "requires_api_key": capability.requires_user_api_key,
                "developer_managed": capability.developer_managed,
            }
            for capability in get_model_profiles().available_providers()
        ]
    }


@app.post("/model-profiles/{profile_id}/diagnose")
async def diagnose_model_profile(
    profile_id: int,
    check_upstream: bool = False,
    portable_session: str | None = Cookie(default=None),
):
    user_id, _ = await _get_session_context(portable_session)
    if check_upstream and not await _acquire_provider_diagnostic_slot(
        user_id, profile_id
    ):
        raise HTTPException(
            status_code=429,
            detail="Подождите перед следующей проверкой провайдера.",
            headers={"Retry-After": str(PROVIDER_DIAGNOSTIC_COOLDOWN)},
        )
    try:
        result = await get_model_profiles().diagnose(
            user_id, profile_id, check_upstream
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "profile_id": result.profile_id,
        "provider": result.provider.value,
        "model_name": result.model_name,
        "status": result.status,
        "message": result.message,
        "upstream_checked": result.upstream_checked,
    }


@app.post("/model-profiles")
async def create_model_profile(
    body: CreateModelProfileRequest,
    portable_session: str | None = Cookie(default=None),
):
    user_id, _ = await _get_session_context(portable_session)
    try:
        profile = await get_model_profiles().add(
            user_id,
            body.provider,
            body.model_name,
            body.display_name,
            body.api_key,
        )
    except (ProviderConfigurationError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {
        "id": profile.id,
        "provider": profile.provider.value,
        "model_name": profile.model_name,
        "display_name": profile.display_name,
        "is_active": profile.is_active,
    }


@app.post("/model-profiles/{profile_id}/activate")
async def activate_model_profile(
    profile_id: int,
    portable_session: str | None = Cookie(default=None),
):
    user_id, thread_id = await _get_session_context(portable_session)
    profile = await get_model_profiles().activate(user_id, profile_id)
    clear_session_model(thread_id)
    return {"id": profile.id, "active": True}


@app.delete("/model-profiles/{profile_id}")
async def delete_model_profile(
    profile_id: int,
    portable_session: str | None = Cookie(default=None),
):
    user_id, thread_id = await _get_session_context(portable_session)
    deleted = await get_model_profiles().delete(user_id, profile_id)
    if deleted:
        clear_session_model(thread_id)
    return {"deleted": deleted}


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
async def code_login(body: CodeLoginRequest, request: Request, response: Response):
    cfg = get_config()
    client_id = request.client.host if request.client else "unknown"
    attempts_key = login_attempt_key(client_id)
    attempts = await cfg.redis_client.incr(attempts_key)
    if attempts == 1:
        await cfg.redis_client.expire(attempts_key, LOGIN_ATTEMPT_WINDOW)
    if attempts > LOGIN_ATTEMPT_LIMIT:
        raise HTTPException(status_code=429, detail="Too many login attempts")

    try:
        code = normalize_login_code(body.code)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc

    user_id = await cfg.redis_client.getdel(login_code_key(code))
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
    emit_event("web.authenticated", user_id=int(user_id))
    return {"user_id": int(user_id)}


@app.post("/auth/logout")
async def logout(
    response: Response,
    portable_session: str | None = Cookie(default=None),
):
    redis = get_config().redis_client
    if portable_session:
        thread_id = await redis.get(f"{SESSION_THREAD_PREFIX}{portable_session}")
        await redis.delete(
            f"{SESSION_KEY_PREFIX}{portable_session}",
            f"{SESSION_THREAD_PREFIX}{portable_session}",
        )
        if thread_id:
            clear_session_model(thread_id)
    response.delete_cookie(SESSION_COOKIE)
    emit_event("web.logout")
    return {"logged_out": True}


@app.get("/auth/me")
async def current_user(portable_session: str | None = Cookie(default=None)):
    user_id, _ = await _get_session_context(portable_session)
    return {"user_id": user_id}


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
    user_id, thread_id = await _get_session_context(portable_session)
    profiles = await get_model_profiles().list(user_id)
    active_profile = next((profile for profile in profiles if profile.is_active), None)
    llm = await get_user_model(user_id) or get_session_model(thread_id)
    return {
        "session_id": thread_id,
        "active_model": _model_id(llm),
        "active_profile_id": active_profile.id if active_profile else None,
        "source": "profile" if active_profile else "operator_fallback",
    }


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
    emit_event("web.websocket.connected", user_id=user_id, thread_id=thread_id)
    logger.info(f"WebSocket connected: session={thread_id}")

    listener_task = asyncio.create_task(_redis_listener(thread_id, websocket))
    thread_lock = _THREAD_LOCKS.setdefault(thread_id, asyncio.Lock())
    message_times = _THREAD_MESSAGE_TIMES.setdefault(thread_id, deque())

    try:
        while True:
            data = await websocket.receive_text()
            text = data.strip()
            if not text:
                continue
            if len(text) > MAX_WEBSOCKET_MESSAGE_SIZE:
                await websocket.send_json({
                    "type": "error",
                    "content": "Message is too large",
                })
                continue
            now = time.monotonic()
            while message_times and now - message_times[0] >= WEBSOCKET_RATE_WINDOW:
                message_times.popleft()
            if len(message_times) >= WEBSOCKET_RATE_LIMIT:
                await websocket.send_json({
                    "type": "error",
                    "content": "Too many messages, please wait",
                })
                continue
            message_times.append(now)

            try:
                async with thread_lock:
                    agent = await get_agent(thread_id, user_id)
                    llm = await get_user_model(user_id) or get_session_model(thread_id)
                    invoker = AgentInvoker(agent, thread_id)
                    response = await asyncio.wait_for(
                        invoker.invoke(
                            user_message=text,
                            runnable_config=cfg.RUNNABLE_CONFIG,
                            llm=llm,
                            sender=WebSocketSender(websocket),
                        ),
                        timeout=AGENT_INVOKE_TIMEOUT,
                    )

                html = MessageRenderer.for_web(response)
                await websocket.send_json({"type": "message", "content": html})

            except Exception as error:
                logger.exception("Agent error for session={}", thread_id)
                await websocket.send_json({
                    "type": "error",
                    "content": f"⚠️ {provider_user_message(error)}",
                })

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected: session={session_id}")
    finally:
        listener_task.cancel()
        with suppress(asyncio.CancelledError):
            await listener_task
        _THREAD_LOCKS.pop(thread_id, None)
        _THREAD_MESSAGE_TIMES.pop(thread_id, None)
        emit_event("web.websocket.disconnected", user_id=user_id, thread_id=thread_id)