from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from zoneinfo import ZoneInfoNotFoundError
from mcp.server.fastmcp import FastMCP
from loguru import logger
from utils.const import MCP_REMINDERS_PORT
from src.services.tool_result import tool_failure, tool_success

mcp = FastMCP(name="Reminders", port=MCP_REMINDERS_PORT, host="0.0.0.0")


@mcp.tool(description="Returns current time in user's timezone. Always call this before creating reminders to know the exact current time.")
def get_current_time(user_timezone: str = "UTC") -> str:
    """
    Args:
        user_timezone: IANA timezone name from user memory (e.g. 'Asia/Krasnoyarsk', 'Europe/Moscow'). Use UTC if unknown.
    """
    try:
        tz = ZoneInfo(user_timezone)
    except (ZoneInfoNotFoundError, ValueError):
        tz = timezone.utc
        user_timezone = "UTC"

    now_local = datetime.now(tz)
    now_utc = datetime.now(timezone.utc)

    return tool_success(
        (
        f"Current time in {user_timezone}: {now_local.strftime('%Y-%m-%d %H:%M:%S %Z')}\n"
        f"Current time in UTC: {now_utc.strftime('%Y-%m-%d %H:%M:%S UTC')}\n"
        f"UTC offset: {now_local.strftime('%z')}\n"
        f"Weekday: {now_local.strftime('%A')}"
        ),
        {
            "timezone": user_timezone,
            "local_time": now_local.isoformat(),
            "utc_time": now_utc.isoformat(),
        },
    )


@mcp.tool(description="Schedule a reminder. Always call get_current_time first to know the current time in user's timezone.")
async def create_reminder(
    user_id: str,
    text: str,
    remind_at: str,
    user_timezone: str = "UTC",
    channel: str = "telegram",
) -> str:
    """
    Args:
        tg_id: Telegram user ID
        text: Reminder text
        remind_at: ISO datetime in user's LOCAL timezone (e.g. '2026-03-14T14:30:00'). Will be converted to UTC automatically.
        user_timezone: IANA timezone name (e.g. 'Asia/Krasnoyarsk'). Use value from user memory.
    """
    from src.tasks.tasks import send_reminder

    try:
        try:
            tz = ZoneInfo(user_timezone)
        except ZoneInfoNotFoundError:
            tz = timezone.utc
            user_timezone = "UTC"

        eta = datetime.fromisoformat(remind_at)
        if eta.tzinfo is None:
            eta = eta.replace(tzinfo=tz)

        eta_utc = eta.astimezone(timezone.utc)
        now_utc = datetime.now(timezone.utc)

        logger.info(f"create_reminder: remind_at={remind_at}, tz={user_timezone}, eta_utc={eta_utc}, now_utc={now_utc}, diff={(eta_utc - now_utc).total_seconds():.0f}s")

        if eta_utc <= now_utc:
            return tool_failure(
                "past_time",
                f"Time {remind_at} ({user_timezone}) is in the past",
                {"current_time": datetime.now(tz).isoformat()},
            )

        send_reminder.apply_async(
            kwargs={"user_id": user_id, "text": text, "channel": channel},
            eta=eta_utc,
        )

        local_str = eta.strftime('%Y-%m-%d %H:%M %Z') if eta.tzinfo else f"{remind_at} ({user_timezone})"
        return tool_success(
            f"Reminder set for {local_str}: «{text}»",
            {"remind_at_utc": eta_utc.isoformat(), "text": text, "channel": channel},
        )

    except (ValueError, TypeError, OSError):
        logger.exception("create_reminder failed")
        return tool_failure(
            "invalid_reminder",
            "Failed to set reminder. Check the time and timezone.",
        )


@mcp.tool(description="Schedule a follow-up message after an event ends.")
async def create_followup(
    tg_id: int,
    event_title: str,
    followup_at: str,
    user_timezone: str = "UTC",
) -> str:
    """
    Args:
        tg_id: Telegram user ID
        event_title: Event name
        followup_at: ISO datetime in user's LOCAL timezone
        user_timezone: IANA timezone name from user memory
    """
    from src.tasks.tasks import followup_after_event

    try:
        try:
            tz = ZoneInfo(user_timezone)
        except ZoneInfoNotFoundError:
            tz = timezone.utc

        eta = datetime.fromisoformat(followup_at)
        if eta.tzinfo is None:
            eta = eta.replace(tzinfo=tz)

        eta_utc = eta.astimezone(timezone.utc)
        now_utc = datetime.now(timezone.utc)

        if eta_utc <= now_utc:
            return tool_failure("past_time", f"Time {followup_at} is in the past")

        followup_after_event.apply_async(
            kwargs={"tg_id": tg_id, "event_title": event_title},
            eta=eta_utc,
        )
        return tool_success(
            f"Follow-up after «{event_title}» scheduled for {followup_at} ({user_timezone})",
            {"followup_at_utc": eta_utc.isoformat(), "event_title": event_title},
        )

    except (ValueError, TypeError, OSError):
        logger.exception("create_followup failed")
        return tool_failure(
            "invalid_followup",
            "Failed to schedule follow-up. Check the time and timezone.",
        )