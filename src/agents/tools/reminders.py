from contextlib import AsyncExitStack
from mcp import ClientSession
from mcp.client.sse import sse_client
from langchain.tools import BaseTool
from langchain_mcp_adapters.tools import load_mcp_tools
from utils.const import MCP_REMINDERS_URL
from loguru import logger

_exit_stack: AsyncExitStack | None = None
_reminders_tools: list[BaseTool] = []


async def init_reminders_client() -> None:
    global _exit_stack, _reminders_tools
    logger.info(f"Connecting to MCP Reminders: {MCP_REMINDERS_URL}")
    _exit_stack = AsyncExitStack()
    read, write = await _exit_stack.enter_async_context(sse_client(MCP_REMINDERS_URL))
    session = await _exit_stack.enter_async_context(ClientSession(read, write))
    await session.initialize()
    _reminders_tools = await load_mcp_tools(session)


async def close_reminders_client() -> None:
    global _exit_stack
    if _exit_stack:
        await _exit_stack.aclose()
        _exit_stack = None


async def get_reminders_tools() -> list[BaseTool]:
    if not _reminders_tools:
        raise RuntimeError("Call init_reminders_client() in start")
    return _reminders_tools