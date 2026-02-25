from mcp.server.fastmcp import FastMCP
from utils.client_session import AsyncHTTPClient
from utils.helpers import format_event
from src.mcp.calendar.models import (
    CreateEventParams, UpdateEventParams,
    EventsRangeParams
)
from utils.const import MCP_CALENDAR_PORT

mcp = FastMCP(name="Google Calendar", port=MCP_CALENDAR_PORT)

@mcp.resource(
        'calendar://events/{tg_id}',
        description="Получить предстоящие события пользователя из Google Calendar"
)
async def get_upcoming_events(tg_id: str) -> str:
    async with AsyncHTTPClient() as api:
        status, data = await api.get("/calendar/events", params={"tg_id": tg_id, "days_ahead": 7})

    if status != 200:
        return f"❌ Ошибка получения событий: {status}"

    events = data.get("events", [])
    if not events:
        return "Нет предстоящих событий"

    lines = []
    for e in events:
        lines.append(format_event(e))
    return "\n".join(lines)


@mcp.resource(
        "calendar://user/{tg_id}", 
        description="Получить информацию о пользователе и статус авторизации в Google Calendar"
)
async def get_user_info(tg_id: str) -> str:
    async with AsyncHTTPClient() as api:
        status, data = await api.get(f"/calendar/users/{tg_id}")

    if status == 404:
        return "❌ Пользователь не найден"
    if status != 200:
        return f"❌ Ошибка: {status}"

    return (
        f"tg_id: {data['tg_id']}\n"
        f"nick: {data.get('tg_nick', '—')}\n"
        f"email: {data.get('email', '—')}\n"
        f"google_authorized: {data.get('has_google_token', False)}"
    )


# TOOLS

@mcp.tool(description="Получить предстоящие события пользователя из Google Calendar")
async def get_events(tg_id: int, days_ahead: int = 7) -> str:
    async with AsyncHTTPClient() as api:
        status, data = await api.get(
            "/calendar/events",
            params={"tg_id": tg_id, "days_ahead": days_ahead}
        )

    if status == 401:
        return "❌ Пользователь не авторизован в Google Calendar"
    if status == 404:
        return "❌ Пользователь не найден"
    if status != 200:
        return f"❌ Ошибка сервера: {status}"

    events = data.get("events", [])
    if not events:
        return "📭 Нет предстоящих событий"

    lines = [f"📅 События на {days_ahead} дней:"]
    for e in events:
        lines.append(format_event(e))
    return "\n".join(lines)


@mcp.tool(description="Найти события по тексту (название, описание, место)")
async def search_events(tg_id: int, query: str, days_ahead: int = 30) -> str:
    """
    Args:
        tg_id: Telegram ID пользователя
        query: Поисковый запрос
        days_ahead: Глубина поиска в днях (по умолчанию 30)
    """
    async with AsyncHTTPClient() as api:
        status, data = await api.get(
            "/calendar/events/search",
            params={"tg_id": tg_id, "query": query, "days_ahead": days_ahead}
        )

    if status == 401:
        return "❌ Пользователь не авторизован"
    if status != 200:
        return f"❌ Ошибка сервера: {status}"

    events = data.get("events", [])
    if not events:
        return f"🔍 По запросу «{query}» ничего не найдено"

    lines = [f"🔍 Найдено событий по «{query}»: {len(events)}"]
    for e in events:
        lines.append(format_event(e))
    return "\n".join(lines)


@mcp.tool(description="Получить события за диапазон дат (например, с 1 по 28 февраля)")
async def get_events_range(tg_id: int, start: str, end: str) -> str:
    if "T" not in start:
        start = f"{start}T00:00:00Z"
    elif not start.endswith("Z"):
        start = f"{start}Z"

    if "T" not in end:
        end = f"{end}T23:59:59Z"
    elif not end.endswith("Z"):
        end = f"{end}Z"

    payload = EventsRangeParams(
        user_id=tg_id,
        start=start,
        end=end
    )
    async with AsyncHTTPClient() as api:
        status, data = await api.post(
            "/calendar/events/range",
            json=payload.model_dump(mode="json")
        )

    if status == 401:
        return "❌ Пользователь не авторизован"
    if status != 200:
        return f"❌ Ошибка сервера: {status}"

    events = data.get("events", [])
    if not events:
        return f"📭 Нет событий с {start} по {end}"

    lines = [f"📅 События с {start} по {end}: {len(events)} шт."]
    for e in events:
        lines.append(format_event(e))
    return "\n".join(lines)



@mcp.tool(description="Получить подробную информацию о событии по его ID")
async def get_event(tg_id: int, event_id: str) -> str:
    """
    Args:
        tg_id: Telegram ID пользователя
        event_id: ID события в Google Calendar
    """
    async with AsyncHTTPClient() as api:
        status, data = await api.get(
            f"/calendar/events/{event_id}",
            params={"tg_id": tg_id}
        )

    if status == 401:
        return "❌ Пользователь не авторизован"
    if status == 404:
        return f"❌ Событие {event_id} не найдено"
    if status != 200:
        return f"❌ Ошибка сервера: {status}"

    return format_event(data.get("event", {}))

@mcp.tool(description="Получить события на конкретный день (например, 26 февраля 2026)")
async def get_events_by_date(tg_id: int, date: str) -> str:
    """
    Args:
        tg_id: Telegram ID пользователя
        date: Дата в формате YYYY-MM-DD (например, 2026-02-26)
    """
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
        return "❌ Пользователь не авторизован"
    if status != 200:
        return f"❌ Ошибка сервера: {status}"

    events = data.get("events", [])
    if not events:
        return f"📭 На {date} событий нет"

    lines = [f"📅 События на {date}: {len(events)} шт."]
    for e in events:
        lines.append(format_event(e))
    return "\n".join(lines)


@mcp.tool(description="Создать новое событие в Google Calendar")
async def create_event(
    tg_id: int,
    title: str,
    start_time: str,
    end_time: str,
    description: str | None = None,
    location: str | None = None,
    attendees: list[str] | None = None,
    timezone: str = "UTC"
) -> str:
    """
    Args:
        tg_id: Telegram ID пользователя
        title: Название события
        start_time: Начало в ISO формате (2025-03-15T10:00:00)
        end_time: Конец в ISO формате (2025-03-15T11:00:00)
        description: Описание события (опционально)
        location: Место проведения (опционально)
        attendees: Список email участников (опционально)
        timezone: Часовой пояс (по умолчанию UTC)
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
        return "❌ Пользователь не авторизован"
    if status != 200:
        return f"❌ Ошибка сервера: {status} — {data}"

    return format_event(data.get("event", {}))

@mcp.tool(description="Обновить существующее событие в Google Calendar")
async def update_event(
    tg_id: int,
    event_id: str,
    title: str | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
    description: str | None = None,
    location: str | None = None,
    timezone: str = "UTC"
) -> str:
    """
    Args:
        tg_id: Telegram ID пользователя
        event_id: ID события в Google Calendar
        title: Новое название (опционально)
        start_time: Новое время начала ISO (опционально)
        end_time: Новое время конца ISO (опционально)
        description: Новое описание (опционально)
        location: Новое место (опционально)
        timezone: Часовой пояс (по умолчанию UTC)
    """
    payload = UpdateEventParams(
        user_id=tg_id,
        title=title,
        start_time=start_time,
        end_time=end_time,
        description=description,
        location=location,
        timezone=timezone
    )

    async with AsyncHTTPClient() as api:
        status, data = await api.patch(
            f"/calendar/events/{event_id}",
            json=payload.model_dump(mode="json", exclude_none=True)
        )

    if status == 401:
        return "❌ Пользователь не авторизован"
    if status == 404:
        return f"❌ Событие {event_id} не найдено"
    if status != 200:
        return f"❌ Ошибка сервера: {status}"

    return format_event(data.get("event", {}))


@mcp.tool(description="Удалить событие из Google Calendar по его ID")
async def delete_event(tg_id: int, event_id: str) -> str:
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
        return "❌ Пользователь не авторизован"
    if status == 404:
        return f"❌ Событие {event_id} не найдено"
    if status != 200:
        return f"❌ Ошибка сервера: {status}"

    return f"Событие {event_id} удалено"


@mcp.tool(description="Получить ссылку для авторизации пользователя в Google Calendar")
async def get_auth_url(tg_id: int) -> str:
    """
    Args:
        tg_id: Telegram ID пользователя
    """
    async with AsyncHTTPClient() as api:
        status, data = await api.get(
            "/calendar/auth_url",
            params={"tg_id": tg_id}
        )

    if status != 200:
        return f"❌ Не удалось получить ссылку: {status}"

    return f"Ссылка для авторизации:\n{data.get('auth_url')}"


@mcp.tool(description="Проверить, авторизован ли пользователь в Google Calendar")
async def check_auth(tg_id: int) -> str:
    """
    Args:
        tg_id: Telegram ID пользователя
    """
    async with AsyncHTTPClient() as api:
        status, data = await api.get(f"/calendar/users/{tg_id}")

    if status == 404:
        return "❌ Пользователь не найден"
    if status != 200:
        return f"❌ Ошибка сервера: {status}"

    authorized = data.get("has_google_token", False)
    return (
        f"{'Авторизован' if authorized else 'Не авторизован'}\n"
        f"tg_id: {data['tg_id']}\n"
        f"nick: {data.get('tg_nick', '—')}"
    )