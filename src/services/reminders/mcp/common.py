from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def resolve_timezone(user_timezone: str) -> tuple[ZoneInfo, str]:
    try:
        return ZoneInfo(user_timezone), user_timezone
    except (ZoneInfoNotFoundError, ValueError):
        return timezone.utc, "UTC"


def parse_scheduled_datetime(
    value: str,
    user_timezone: str,
) -> tuple[datetime, ZoneInfo, str]:
    tz, normalized_timezone = resolve_timezone(user_timezone)
    scheduled = datetime.fromisoformat(value)
    if scheduled.tzinfo is None:
        scheduled = scheduled.replace(tzinfo=tz)
    return scheduled, tz, normalized_timezone
