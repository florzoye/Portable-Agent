import asyncio
import sys
from loguru import logger
from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.types import BotCommand
from langchain_core.language_models import BaseChatModel
from aiogram.exceptions import TelegramNetworkError, TelegramAPIError

from src.services.telegram.bot.handlers import (
    register_handlers,
    init_telegram_sender,
    on_startup,
    on_shutdown,
)
from data import init, get_config
from utils.model_selector import select_model
from src.agents.llms.initializer import LLMInitializer

selected_llm: BaseChatModel | None = None


def get_selected_llm() -> BaseChatModel:
    if selected_llm is None:
        raise RuntimeError("Model not choose")
    return selected_llm


async def _init_llms() -> tuple:
    llms = await LLMInitializer.initialize()
    wrappers = LLMInitializer.get_wrappers()
    return wrappers, llms


async def _run_bot():
    cfg = get_config()

    session = AiohttpSession(proxy=cfg.TG_SETTINGS.TELEGRAM_PROXY)
    bot = Bot(token=cfg.TG_SETTINGS.BOT_TOKEN, session=session)
    init_telegram_sender(bot)

    dp = Dispatcher(storage=RedisStorage(redis=cfg.redis_client))
    register_handlers(dp)
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)
    await bot.set_my_commands(
        [
            BotCommand(command="start", description="Открыть меню"),
            BotCommand(command="menu", description="Показать меню"),
            BotCommand(command="chat", description="Войти в режим чата"),
            BotCommand(command="cancel", description="Выйти из чата или отменить действие"),
            BotCommand(command="calendar", description="Календарь через чат"),
            BotCommand(command="reminders", description="Напоминания через чат"),
            BotCommand(command="models", description="Мои модели"),
            BotCommand(command="web", description="Код для входа в Web UI"),
            BotCommand(command="help", description="Помощь и примеры"),
        ]
    )

    logger.info("🚀 Start bot...")
    await dp.start_polling(bot)


async def _main():
    try:
        wrappers, llms = await _init_llms()
        selected = await select_model(wrappers, llms)
        LLMInitializer.set_selected(selected)
    except Exception as e:
        logger.error(f"❌ Failed to initialize LLM: {e}")
        sys.exit(1)

    try:
        await _run_bot()
    except TelegramNetworkError as e:
        logger.error(
            "❌ Cannot connect to Telegram API.\n"
            "   Check your network or configure a proxy.\n"
            f"   Reason: {e}"
        )
        sys.exit(1)
    except TelegramAPIError as e:
        logger.error(f"❌ Telegram API error: {e}")
        sys.exit(1)
    except Exception as e:
        logger.exception(f"❌ Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    try:
        init()
        asyncio.run(_main())
    except KeyboardInterrupt:
        logger.info("👋 Bot stopped by user")