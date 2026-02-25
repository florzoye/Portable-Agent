from contextlib import AsyncExitStack
from mcp import ClientSession
from mcp.client.sse import sse_client
from langchain.tools import BaseTool
from langchain_mcp_adapters.tools import load_mcp_tools
from utils.const import MCP_CALENDAR_URL

_exit_stack: AsyncExitStack | None = None
_calendar_client_tools: list[BaseTool] = []


async def init_calendar_client() -> None:
    global _exit_stack, _calendar_client_tools

    _exit_stack = AsyncExitStack()
    read, write = await _exit_stack.enter_async_context(sse_client(MCP_CALENDAR_URL))
    session = await _exit_stack.enter_async_context(ClientSession(read, write))
    await session.initialize()
    _calendar_client_tools = await load_mcp_tools(session)


async def close_calendar_client() -> None:
    global _exit_stack
    if _exit_stack:
        await _exit_stack.aclose()
        _exit_stack = None


async def get_calendar_tools() -> list[BaseTool]:
    if not _calendar_client_tools:
        raise RuntimeError("Вызови init_calendar_client() при старте")
    return _calendar_client_tools