from langchain_core.tools import BaseTool

_tools: list[BaseTool] | None = None


async def get_tools() -> list[BaseTool]:
    global _tools
    if _tools is not None:
        return _tools

    from src.agents.tools.calendar import init_calendar_client, get_calendar_tools
    from src.agents.tools.reminders import init_reminders_client, get_reminders_tools

    await init_calendar_client()
    await init_reminders_client()

    _tools = [
        *await get_calendar_tools(),
        *await get_reminders_tools(),
    ]
    return _tools   