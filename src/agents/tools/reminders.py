import asyncio
from mcp import ClientSession
from mcp.client.sse import sse_client
from langchain.tools import BaseTool
from langchain_mcp_adapters.tools import load_mcp_tools
from loguru import logger
from utils.const import MCP_REMINDERS_URL

_reminders_tools: list[BaseTool] = []
_keeper_task: asyncio.Task | None = None
_ready_event: asyncio.Event | None = None
_stop_event: asyncio.Event | None = None


async def _session_keeper(ready: asyncio.Event, stop: asyncio.Event) -> None:
    global _reminders_tools
    logger.info(f"Connecting to MCP Reminders: {MCP_REMINDERS_URL}")
    try:
        async with sse_client(MCP_REMINDERS_URL) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                _reminders_tools = await load_mcp_tools(session)
                ready.set()
                await stop.wait()
    except Exception:
        logger.exception("Reminders MCP session error")
    finally:
        _reminders_tools = []
        ready.set()


async def init_reminders_client() -> None:
    global _keeper_task, _ready_event, _stop_event

    if _keeper_task is not None and not _keeper_task.done():
        return

    _ready_event = asyncio.Event()
    _stop_event = asyncio.Event()
    _keeper_task = asyncio.create_task(
        _session_keeper(_ready_event, _stop_event),
        name="reminders-mcp-keeper",
    )
    await _ready_event.wait()


async def close_reminders_client() -> None:
    global _keeper_task, _stop_event

    if _stop_event:
        _stop_event.set()

    if _keeper_task and not _keeper_task.done():
        try:
            await asyncio.wait_for(_keeper_task, timeout=5.0)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            _keeper_task.cancel()

    _keeper_task = None
    _stop_event = None
    _ready_event = None


async def get_reminders_tools() -> list[BaseTool]:
    if not _reminders_tools:
        raise RuntimeError("Call init_reminders_client() first")
    return _reminders_tools