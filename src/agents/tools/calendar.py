from contextlib import AsyncExitStack
from mcp import ClientSession
from mcp.client.sse import sse_client
from langchain.tools import BaseTool
from langchain_mcp_adapters.tools import load_mcp_tools
from loguru import logger
from utils.const import MCP_CALENDAR_URL

_exit_stack: AsyncExitStack | None = None
_calendar_client_tools: list[BaseTool] = []


async def init_calendar_client() -> None:
    global _exit_stack, _calendar_client_tools

    if _exit_stack is not None:
        return

    stack = AsyncExitStack()
    read, write = await stack.enter_async_context(sse_client(MCP_CALENDAR_URL))
    session = await stack.enter_async_context(ClientSession(read, write))
    await session.initialize()

    _calendar_client_tools = await load_mcp_tools(session)
    _exit_stack = stack


async def close_calendar_client() -> None:
    global _exit_stack, _calendar_client_tools

    if _exit_stack:
        try:
            await _exit_stack.aclose()
        except Exception as e:
            logger.exception(f"Error while closing calendar client: {e}")
        finally:
            _exit_stack = None
            _calendar_client_tools = []


async def get_calendar_tools() -> list[BaseTool]:
    if not _calendar_client_tools:
        raise RuntimeError("Call init_calendar_client() in start")
    return _calendar_client_tools