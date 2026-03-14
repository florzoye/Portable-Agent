from loguru import logger
from aiogram.types import Message
from aiogram.enums import ContentType
from aiogram import Bot, Dispatcher, F

from src.factories.tools_factory import get_tools
from src.agents.llms.initializer import LLMInitializer
from src.services.telegram.bot.dependencies import get_agent
from src.factories.checkpointer_factory import get_checkpointer, close_checkpointer
from src.agents.tools.reminders import close_reminders_client
from src.agents.tools.calendar import close_calendar_client


from utils.helpers import _md_to_html
from data import get_config

_bot: Bot | None = None
MAX_MESSAGE_LEN = 4096


def init_telegram_sender(bot: Bot) -> None:
    global _bot
    _bot = bot



async def on_startup():
    await get_tools()  
    await LLMInitializer.initialize()
    await get_checkpointer()
    logger.info("🤖 Assistant started")

async def on_shutdown():
    await close_calendar_client()
    await close_reminders_client()
    await close_checkpointer()
    logger.info("🤖 Assistant stopped")

async def _send_html(message: Message, text: str) -> None:
    html = _md_to_html(text)
    for chunk in [html[i:i + MAX_MESSAGE_LEN] for i in range(0, len(html), MAX_MESSAGE_LEN)]:
        await message.answer(chunk, parse_mode="HTML", disable_web_page_preview=True)


async def send_message(tg_id: int, text: str) -> None:
    if _bot is None:
        raise RuntimeError("Telegram bot not initialized")
    html = _md_to_html(text)
    for chunk in [html[i:i + MAX_MESSAGE_LEN] for i in range(0, len(html), MAX_MESSAGE_LEN)]:
        await _bot.send_message(chat_id=tg_id, text=chunk, parse_mode="HTML", disable_web_page_preview=True)


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
            await _send_html(message, response)

        except Exception as e:
            logger.exception(f"Agent error for tg_id={tg_id}: {e}")
            await message.answer("⚠️ An error has occurred, try again")

    @dp.message(F.content_type == ContentType.PHOTO)
    async def handle_photo(message: Message):
        await message.answer("🖼️ I can't understand images yet")

    @dp.message(F.content_type == ContentType.VIDEO)
    async def handle_video(message: Message):
        await message.answer("📹 I can't understand videos yet")

    @dp.message(F.content_type == ContentType.VOICE)
    async def handle_voice(message: Message):
        await message.answer("🎤 I can't understand voice messages yet")

    @dp.message()
    async def handle_other(message: Message):
        await message.answer("🤔 I can only work with text for now")