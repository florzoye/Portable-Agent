from typing import Any

from utils.client_session import AsyncHTTPClient
from utils.helpers import format_event
from src.services.tool_result import tool_failure, tool_success


async def calendar_request(
    method: str,
    path: str,
    *,
    params: dict | None = None,
    payload: dict | None = None,
) -> tuple[int, Any]:
    async with AsyncHTTPClient() as api:
        request = getattr(api, method)
        if method == "get" or method == "delete":
            return await request(path, params=params)
        return await request(path, json=payload)


def event_list_result(
    status: int,
    data: Any,
    *,
    empty_message: str,
    heading: str,
) -> dict:
    if status == 401:
        return tool_failure("not_authorized", "The user is not authorized in Google Calendar")
    if status == 404:
        return tool_failure("user_not_found", "The user was not found")
    if status != 200:
        return tool_failure("server_error", f"Calendar service error ({status})", {"status": status})
    if not isinstance(data, dict):
        return tool_failure("invalid_response", "Incorrect response from calendar service")

    events = data.get("events", [])
    if not events:
        return tool_success(empty_message, {"events": []})

    return tool_success(
        "\n".join([heading, *(format_event(event) for event in events)]),
        {"events": events},
    )


def event_result(status: int, data: Any, event_id: str | None = None) -> dict:
    if status == 401:
        return tool_failure("not_authorized", "The user is not authorized in Google Calendar")
    if status == 404 and event_id is not None:
        return tool_failure("event_not_found", f"Event {event_id} not found")
    if status != 200:
        return tool_failure("server_error", f"Calendar service error ({status})", {"status": status})
    if not isinstance(data, dict):
        return tool_failure("invalid_response", "Incorrect response from calendar service")

    event = data.get("event", {})
    return tool_success(format_event(event), {"event": event})
