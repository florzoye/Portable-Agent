import asyncio
import sys
from loguru import logger
from aiogram import Bot, Dispatcher
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

    bot = Bot(token=cfg.TG_SETTINGS.BOT_TOKEN)
    init_telegram_sender(bot)

    dp = Dispatcher()
    register_handlers(dp)
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

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