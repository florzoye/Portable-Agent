from mcp import ClientSession
from mcp.client.sse import sse_client

from langchain.tools import BaseTool
from langchain_mcp_adapters.tools import load_mcp_tools

from utils.const import MCP_CALENDAR_URL

async def get_calendar_tools() -> list[BaseTool]:
     async with sse_client(MCP_CALENDAR_URL) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            return await load_mcp_tools(session)