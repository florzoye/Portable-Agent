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

    if _exit_stack is not None:
        return

    logger.info(f"Connecting to MCP Reminders: {MCP_REMINDERS_URL}")

    stack = AsyncExitStack()
    read, write = await stack.enter_async_context(sse_client(MCP_REMINDERS_URL))
    session = await stack.enter_async_context(ClientSession(read, write))
    await session.initialize()

    _reminders_tools = await load_mcp_tools(session)
    _exit_stack = stack


async def close_reminders_client() -> None:
    global _exit_stack, _reminders_tools

    if _exit_stack:
        try:
            await _exit_stack.aclose()
        except Exception as e:
            logger.exception(f"Error while closing reminders client: {e}")
        finally:
            _exit_stack = None
            _reminders_tools = []


async def get_reminders_tools() -> list[BaseTool]:
    if not _reminders_tools:
        raise RuntimeError("Call init_reminders_client() in start")
    return _reminders_tools