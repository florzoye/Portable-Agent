import asyncio
from loguru import logger
from aiogram.types import Message
from aiogram.enums import ContentType
from aiogram import Bot, Dispatcher, F

from src.agents.llms.initializer import LLMInitializer
from src.agents.tools.calendar import init_calendar_client, close_calendar_client
from src.factories.checkpointer_factory import get_checkpointer, close_checkpointer
from src.services.telegram.bot.dependencies import get_agent
from data import get_config

_bot: Bot | None = None
_main_loop: asyncio.AbstractEventLoop | None = None


def init_telegram_sender(bot: Bot) -> None:
    global _bot
    _bot = bot


def set_main_loop(loop: asyncio.AbstractEventLoop) -> None:
    global _main_loop
    _main_loop = loop


async def on_startup():
    await init_calendar_client()
    await LLMInitializer.initialize()

    await get_checkpointer()

    logger.info("🤖 Ассистент запущен")


async def on_shutdown():
    await close_calendar_client()
    await close_checkpointer()
    logger.info("🤖 Ассистент остановлен")


async def send_message(tg_id: int, text: str) -> None:
    if _bot is None:
        raise RuntimeError("Telegram bot not initialized")

    await _bot.send_message(
        chat_id=tg_id,
        text=text,
        disable_web_page_preview=True,
    )


def register_handlers(dp: Dispatcher):

    @dp.message(F.text)
    async def handle_text(message: Message):
        tg_id = message.from_user.id
        text = message.text.strip()
        cfg = get_config()

        try:
            agent = await get_agent(tg_id)

            result = await agent.ainvoke(
                {"messages": [{"role": "user", "content": text}]},
                config={
                    "configurable": {"thread_id": str(tg_id)},
                    **cfg.RUNNABLE_CONFIG,
                },
            )

            response = result["messages"][-1].content
            await message.answer(response)

        except Exception as e:
            logger.exception(f"Agent error for tg_id={tg_id}: {e}")
            await message.answer("⚠️ Произошла ошибка, попробуй ещё раз")

    @dp.message(F.content_type == ContentType.PHOTO)
    async def handle_photo(message: Message):
        await message.answer("🖼️ Пока я не умею понимать изображения")

    @dp.message(F.content_type == ContentType.VIDEO)
    async def handle_video(message: Message):
        await message.answer("📹 Пока я не умею понимать видео")

    @dp.message(F.content_type == ContentType.VOICE)
    async def handle_voice(message: Message):
        await message.answer("🎤 Пока я не умею понимать голосовые сообщения")

    @dp.message()
    async def handle_other(message: Message):
        await message.answer("🤔 Пока я могу работать только с текстом")