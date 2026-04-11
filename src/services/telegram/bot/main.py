import asyncio
from loguru import logger
from aiogram import Bot, Dispatcher
from langchain_core.language_models import BaseChatModel

from src.services.telegram.bot.handlers import (
    register_handlers,
    init_telegram_sender,
    on_startup,
    on_shutdown,
)
from src.agents.llms.initializer import LLMInitializer
from utils.model_selector import select_model
from data import init, get_config

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


if __name__ == "__main__":
    try:
        init()

        async def _main():
            wrappers, llms = await _init_llms()
            selected = await select_model(wrappers, llms)
            LLMInitializer.set_selected(selected)
            await _run_bot()

        asyncio.run(_main())

    except KeyboardInterrupt:
        pass