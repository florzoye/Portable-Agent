from mcp.server.fastmcp import FastMCP
from utils.client_session import AsyncHTTPClient
from utils.helpers import format_event
from src.services.calendar.mcp.models import (
    CreateEventParams, UpdateEventParams,
    EventsRangeParams
)
from utils.const import MCP_CALENDAR_PORT
from src.services.tool_result import tool_failure, tool_success
from src.services.calendar.mcp.common import (
    calendar_request,
    event_list_result,
    event_result,
)

mcp = FastMCP(name="Google Calendar", port=MCP_CALENDAR_PORT, host="0.0.0.0")

@mcp.resource(
        'calendar://events/{tg_id}',
        description="Get user's upcoming events from Google Calendar"
)
async def get_upcoming_events(tg_id: str) -> str:
    async with AsyncHTTPClient() as api:
        status, data = await api.get("/calendar/events", params={"tg_id": tg_id, "days_ahead": 7})

    if status != 200:
        return f"❌ Error receiving events: {status}"

    events = data.get("events", [])
    if not events:
        return "There are no upcoming events"

    lines = []
    for e in events:
        lines.append(format_event(e))
    return "\n".join(lines)


@mcp.resource(
        "calendar://user/{tg_id}", 
        description="Get user information and authorization status in Google Calendar"
)
async def get_user_info(tg_id: str) -> str:
    async with AsyncHTTPClient() as api:
        status, data = await api.get(f"/calendar/users/{tg_id}")

    if status == 404:
        return "❌ User not found"
    if status != 200:
        return f"❌ Error: {status}"

    return (
        f"tg_id: {data['tg_id']}\n"
        f"nick: {data.get('tg_nick', '—')}\n"
        f"email: {data.get('email', '—')}\n"
        f"google_authorized: {data.get('has_google_token', False)}"
    )


# TOOLS

@mcp.tool(description="Get user's upcoming events from Google Calendar")
async def get_events(tg_id: int, days_ahead: int = 7) -> dict:
    status, data = await calendar_request(
        "get",
        "/calendar/events",
        params={"tg_id": tg_id, "days_ahead": days_ahead},
    )
    return event_list_result(
        status,
        data,
        empty_message="There are no upcoming events",
        heading=f"Events for {days_ahead} days:",
    )


@mcp.tool(description="Find events by text (name, description, location)")
async def search_events(tg_id: int, query: str, days_ahead: int = 30) -> dict:
    """
    Args:
        tg_id: Telegram ID user
        query:Search query
        days_ahead: Search depth in days (default is 30)
    """
    status, data = await calendar_request(
        "get",
        "/calendar/events/search",
        params={"tg_id": tg_id, "query": query, "days_ahead": days_ahead},
    )

    return event_list_result(
        status,
        data,
        empty_message=f"No results found for {query}",
        heading=f"Events found by «{query}»: {len(data.get('events', [])) if isinstance(data, dict) else 0}",
    )

@mcp.tool(description="Get events for a date range")
async def get_events_range(tg_id: int, start: str, end: str) -> dict:
    if "T" not in start:
        start = f"{start}T00:00:00Z"
    if "T" not in end:
        end = f"{end}T23:59:59Z"

    payload = EventsRangeParams(
        user_id=tg_id,
        start=start,
        end=end
    )

    status, data = await calendar_request(
        "post",
        "/calendar/events/range",
        payload=payload.model_dump(mode="json"),
    )
    return event_list_result(
        status,
        data,
        empty_message=f"No events from {start} to {end}",
        heading=f"Events from {start} to {end}: {len(data.get('events', [])) if isinstance(data, dict) else 0} events",
    )


@mcp.tool(description="Get detailed information about an event by its ID")
async def get_event(tg_id: int, event_id: str) -> dict:
    """
    Args:
        tg_id: Telegram ID user
        event_id: ID event in Google Calendar
    """
    async with AsyncHTTPClient() as api:
        status, data = await api.get(
            f"/calendar/events/{event_id}",
            params={"tg_id": tg_id}
        )

    if status == 401:
        return tool_failure("not_authorized", "User is not authorized")
    if status == 404:
        return tool_failure("event_not_found", f"Event {event_id} not found")
    if status != 200:
        return tool_failure("server_error", f"Server error: {status}", {"status": status})

    return tool_success(
        format_event(data.get("event", {})),
        {"event": data.get("event", {})},
    )

@mcp.tool(description="Get events for a specific day")
async def get_events_by_date(tg_id: int, date: str) -> dict:
    payload = EventsRangeParams(
        user_id=tg_id,
        start=f"{date}T00:00:00Z",
        end=f"{date}T23:59:59Z"
    )

    async with AsyncHTTPClient() as api:
        status, data = await api.post(
            "/calendar/events/range",
            json=payload.model_dump(mode="json")
        )

    if status == 401:
        return tool_failure("not_authorized", "The user is not authorized in Google Calendar")

    if status != 200:
        return tool_failure("server_error", f"Calendar service error ({status})", {"status": status})

    if not isinstance(data, dict):
        return tool_failure("invalid_response", "Incorrect response from calendar service")

    events = data.get("events", [])
    if not events:
        return tool_success(f"There are no events on {date}", {"events": []})

    lines = [f"📅 Events on {date}: {len(events)} events"]
    for e in events:
        lines.append(format_event(e))
    return tool_success("\n".join(lines), {"events": events})

@mcp.tool(description="Create a new event in Google Calendar")
async def create_event(
    tg_id: int,
    title: str,
    start_time: str,
    end_time: str,
    description: str | None = None,
    location: str | None = None,
    attendees: list[str] | None = None,
    timezone: str = "UTC"
) -> dict:
    """
    Args:
        tg_id: Telegram user ID
        title: Event title
        start_time: Start in ISO format (2025-03-15T10:00:00)
        end_time: End in ISO format (2025-03-15T11:00:00)
        description: Event description (optional)
        location: Event location (optional)
        attendees: List of attendees' emails (optional)
        timezone: Time zone (default: UTC)
    """
    if attendees is None:
        attendees = []

    payload = CreateEventParams(
        user_id=tg_id,
        title=title,
        start_time=start_time,
        end_time=end_time,
        description=description,
        location=location,
        attendees=attendees,
        timezone=timezone
    )

    async with AsyncHTTPClient() as api:
        status, data = await api.post(
            "/calendar/events",
            json=payload.model_dump(mode="json")
        )

    if status == 401:
        return tool_failure("not_authorized", "The user is not logged in")
    if status != 200:
        return tool_failure("server_error", f"Calendar service error ({status})", {"status": status})

    return tool_success(
        format_event(data.get("event", {})),
        {"event": data.get("event", {})},
    )

@mcp.tool(description="Update an existing event in Google Calendar")
async def update_event(
    tg_id: int,
    event_id: str,
    title: str | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
    description: str | None = None,
    location: str | None = None,
    attendees: list[str] | None = None,
    timezone: str = "UTC"
) -> dict:
    """
    Args:
        tg_id: Telegram user ID
        event_id: Google Calendar event ID
        title: New title (optional)
        start_time: New start ISO time (optional)
        end_time: New end ISO time (optional)
        description: New description (optional)
        location: New location (optional)
        timezone: Time zone (default UTC)
    """
    payload = UpdateEventParams(
        user_id=tg_id,
        title=title,
        start_time=start_time,
        end_time=end_time,
        description=description,
        location=location,
        attendees=attendees,
        timezone=timezone
    )

    async with AsyncHTTPClient() as api:
        status, data = await api.patch(
            f"/calendar/events/{event_id}",
            json=payload.model_dump(mode="json", exclude_none=True)
        )

    if status == 401:
        return tool_failure("not_authorized", "The user is not logged in")
    if status == 404:
        return tool_failure("event_not_found", f"Event {event_id} not found")
    if status != 200:
        return tool_failure("server_error", f"Server error: {status}", {"status": status})

    return tool_success(
        format_event(data.get("event", {})),
        {"event": data.get("event", {})},
    )


@mcp.tool(description="Delete an event from Google Calendar by its ID")
async def delete_event(tg_id: int, event_id: str) -> dict:
    """
    Args:
        tg_id: Telegram ID пользователя
        event_id: ID события в Google Calendar
    """
    async with AsyncHTTPClient() as api:
        status, _ = await api.delete(
            f"/calendar/events/{event_id}",
            params={"tg_id": tg_id}
        )

    if status == 401:
        return tool_failure("not_authorized", "The user is not logged in")
    if status == 404:
        return tool_failure("event_not_found", f"Event {event_id} not found")
    if status != 200:
        return tool_failure("server_error", f"Server error: {status}", {"status": status})

    return tool_success(f"Event {event_id} has been deleted", {"event_id": event_id})


@mcp.tool(description="Get a link to authorize a user in Google Calendar")
async def get_auth_url(tg_id: int) -> dict:
    """
    Args:
        tg_id: Telegram ID user
    """
    async with AsyncHTTPClient() as api:
        status, data = await api.get(
            "/calendar/auth_url",
            params={"tg_id": tg_id}
        )

    if status != 200:
        return tool_failure("server_error", f"Failed to retrieve the link: {status}", {"status": status})

    return tool_success(
        f"Authorization link:\n{data.get('auth_url')}",
        {"auth_url": data.get("auth_url")},
    )


@mcp.tool(description="Check if the user is authorized in Google Calendar")
async def check_auth(tg_id: int) -> dict:
    """
    Args:
        tg_id: Telegram ID user
    """
    async with AsyncHTTPClient() as api:
        status, data = await api.get(f"/calendar/users/{tg_id}")

    if status == 401:
        return tool_failure("not_authorized", "The user is not logged in")
    if status != 200:
        return tool_failure("server_error", f"Server error: {status}", {"status": status})

    authorized = data.get("has_google_token", False)
    return tool_success(
        (
            f"{'Authorized' if authorized else 'Not authorized'}\n"
            f"tg_id: {data['tg_id']}\n"
            f"nick: {data.get('tg_nick', '—')}"
        ),
        {"authorized": authorized, "tg_id": data["tg_id"]},
    )