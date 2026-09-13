from collections.abc import Awaitable, Callable
from typing import Any

from langchain.agents.middleware.types import AgentMiddleware, ToolCallRequest
from langchain_core.messages import ToolMessage
from langgraph.types import Command


class UserContextMiddleware(AgentMiddleware):
    """Bind calendar and reminder tools to the server-owned user context."""

    _calendar_tools = {
        "get_events",
        "search_events",
        "get_events_range",
        "get_event",
        "get_events_by_date",
        "create_event",
        "update_event",
        "delete_event",
        "get_auth_url",
        "check_auth",
    }

    def __init__(self, user_id: int | str, channel: str):
        self.user_id = str(user_id)
        self.channel = channel

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command[Any]]],
    ) -> ToolMessage | Command[Any]:
        tool_name = request.tool_call["name"]
        if tool_name not in self._calendar_tools and tool_name not in {
            "create_reminder",
            "create_followup",
        }:
            return await handler(request)

        args = dict(request.tool_call.get("args") or {})
        if tool_name in self._calendar_tools:
            args["tg_id"] = self._coerce_calendar_id()
        elif tool_name == "create_reminder":
            args["user_id"] = self.user_id
            args["channel"] = self.channel
        else:
            args["tg_id"] = self._coerce_calendar_id()

        bound_call = {**request.tool_call, "args": args}
        return await handler(request.override(tool_call=bound_call))

    def _coerce_calendar_id(self) -> int | str:
        try:
            return int(self.user_id)
        except ValueError:
            return self.user_id
