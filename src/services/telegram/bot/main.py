import asyncio
from loguru import logger
from aiogram import Bot, Dispatcher

from src.services.calendar.mcp.server import mcp
from src.services.telegram.bot.handlers import (
    register_handlers,
    init_telegram_sender,
    on_startup,
    on_shutdown,
    set_main_loop,
)
from data import init, get_config


async def main():
    init()
    cfg = get_config()

    loop = asyncio.get_event_loop()
    set_main_loop(loop)

    bot = Bot(token=cfg.TG_SETTINGS.BOT_TOKEN)
    init_telegram_sender(bot)

    dp = Dispatcher()
    register_handlers(dp)
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    logger.info("🚀 Запуск бота...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())