import asyncio
from celery import shared_task
from loguru import logger


def _run(coro):
    return asyncio.run(coro)


async def _send_telegram(tg_id: int, text: str):
    """Send a message directly via Telegram Bot API."""
    from utils.client_session import AsyncHTTPClient
    from data import get_config

    cfg = get_config()
    token = cfg.TG_SETTINGS.BOT_TOKEN

    async with AsyncHTTPClient() as client:
        status, data = await client.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": tg_id, "text": text, "parse_mode": "HTML"}
        )
    if status != 200:
        raise RuntimeError(f"Telegram API error: {status} — {data}")


async def _ask(tg_id: int, content: str) -> str:
    """Invoke the agent for a user and return the response."""
    from src.agents.llms.initializer import LLMInitializer
    from src.services.telegram.bot.dependencies import get_agent
    from data import get_config

    await LLMInitializer.initialize()
    agent = await get_agent(tg_id)
    cfg = get_config()

    result = await agent.ainvoke(
        {"messages": [{"role": "user", "content": content}]},
        config={
            "configurable": {"thread_id": str(tg_id)},
            **cfg.RUNNABLE_CONFIG,
        },
    )
    return result["messages"][-1].content


@shared_task(name="tasks.send_reminder", bind=True, max_retries=3)
def send_reminder(self, tg_id: int, text: str):
    """Send a reminder message to the user via Telegram."""
    try:
        _run(_send_telegram(tg_id, f"🔔 Reminder: {text}"))
        logger.info(f"Reminder sent to tg_id={tg_id}")
    except Exception as e:
        logger.error(f"Failed to send reminder: {e}")
        raise self.retry(exc=e, countdown=60)


@shared_task(name="tasks.followup_after_event", bind=True, max_retries=2)
def followup_after_event(self, tg_id: int, event_title: str):
    """Send a follow-up message after an event ends."""
    try:
        content = (
            f"[SYSTEM: Событие '{event_title}' только что завершилось. "
            f"Напиши пользователю короткое неформальное сообщение — "
            f"спроси как всё прошло. Одно-два предложения, без лишнего.]"
        )
        response = _run(_ask(tg_id, content))
        _run(_send_telegram(tg_id, response))
        logger.info(f"Follow-up for '{event_title}' sent to tg_id={tg_id}")
    except Exception as e:
        logger.error(f"Follow-up failed: {e}")
        raise self.retry(exc=e, countdown=120)


@shared_task(name="tasks.check_finished_events")
def check_finished_events():
    """Check events that ended 10-20 min ago and schedule follow-ups. Runs every 5 min via Celery Beat."""
    from datetime import datetime, timezone, timedelta
    from utils.client_session import AsyncHTTPClient

    async def _check():
        now = datetime.now(timezone.utc)
        start = (now - timedelta(minutes=20)).isoformat()
        end = (now - timedelta(minutes=10)).isoformat()

        async with AsyncHTTPClient() as api:
            status, data = await api.get("/calendar/users/active")

        if status != 200 or not data:
            logger.warning(f"Failed to get active users: {status}")
            return

        from data import get_config
        cfg = get_config()
        redis = cfg.redis_client

        for user in data.get("users", []):
            tg_id = user["tg_id"]

            async with AsyncHTTPClient() as api:
                status, events_data = await api.post(
                    "/calendar/events/range",
                    json={"user_id": tg_id, "start": start, "end": end}
                )

            if status != 200:
                logger.warning(f"Failed to get events for tg_id={tg_id}: {status}")
                continue

            for event in events_data.get("events", []):
                event_id = event.get("id")
                title = event.get("title", "event")
                key = f"followup_sent:{tg_id}:{event_id}"

                if await redis.exists(key):
                    continue

                followup_after_event.delay(tg_id=tg_id, event_title=title)
                await redis.setex(key, 86400, "1")
                logger.info(f"Follow-up scheduled: '{title}' for tg_id={tg_id}")

    _run(_check())


@shared_task(name="tasks.morning_digest")
def morning_digest():
    """Send morning digest of today's events to all active users. Runs daily at 09:00 UTC via Celery Beat."""
    from datetime import datetime, timezone

    async def _send():
        from utils.client_session import AsyncHTTPClient
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        async with AsyncHTTPClient() as api:
            status, data = await api.get("/calendar/users/active")

        if status != 200 or not data:
            logger.warning(f"Failed to get active users: {status}")
            return

        for user in data.get("users", []):
            tg_id = user["tg_id"]
            try:
                content = (
                    f"[SYSTEM: Сейчас утро {today}. "
                    f"Посмотри события пользователя на сегодня и пришли краткую сводку дня. "
                    f"Учти предпочтения пользователя из памяти.]"
                )
                response = await _ask(tg_id, content)
                await _send_telegram(tg_id, response)
                logger.info(f"Morning digest sent to tg_id={tg_id}")
            except Exception as e:
                logger.error(f"Morning digest failed for tg_id={tg_id}: {e}")

    _run(_send())