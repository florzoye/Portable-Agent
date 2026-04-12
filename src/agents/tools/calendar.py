import asyncio
from mcp import ClientSession
from mcp.client.sse import sse_client
from langchain.tools import BaseTool
from langchain_mcp_adapters.tools import load_mcp_tools
from loguru import logger
from utils.const import MCP_CALENDAR_URL

_calendar_client_tools: list[BaseTool] = []
_keeper_task: asyncio.Task | None = None
_ready_event: asyncio.Event | None = None
_stop_event: asyncio.Event | None = None


async def _session_keeper(ready: asyncio.Event, stop: asyncio.Event) -> None:
    global _calendar_client_tools
    try:
        async with sse_client(MCP_CALENDAR_URL) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                _calendar_client_tools = await load_mcp_tools(session)
                ready.set()
                await stop.wait()
    except Exception:
        logger.exception("Calendar MCP session error")
    finally:
        _calendar_client_tools = []
        ready.set()  # unblock waiters even on failure


async def init_calendar_client() -> None:
    global _keeper_task, _ready_event, _stop_event

    if _keeper_task is not None and not _keeper_task.done():
        return

    _ready_event = asyncio.Event()
    _stop_event = asyncio.Event()
    _keeper_task = asyncio.create_task(
        _session_keeper(_ready_event, _stop_event),
        name="calendar-mcp-keeper",
    )
    await _ready_event.wait()


async def close_calendar_client() -> None:
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


async def get_calendar_tools() -> list[BaseTool]:
    if not _calendar_client_tools:
        raise RuntimeError("Call init_calendar_client() first")
    return _calendar_client_tools