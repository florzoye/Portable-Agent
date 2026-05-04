from loguru import logger
from aiogram.filters import Command
from aiogram import Bot, Dispatcher, F
from aiogram.enums import ContentType, ParseMode
from aiogram.types import CallbackQuery, Message, InlineKeyboardButton, InlineKeyboardMarkup

from src.agents.chat import AgentInvoker
from src.factories.tools_factory import get_tools
from src.factories.agents_factory import AgentsFactory
from src.agents.llms.initializer import LLMInitializer
from src.services.telegram.bot.dependencies import get_agent
from src.factories.checkpointer_factory import get_checkpointer, close_checkpointer
from src.agents.tools.reminders import close_reminders_client
from src.agents.tools.calendar import close_calendar_client

from data import get_config

_bot: Bot | None = None
MAX_MESSAGE_LEN = 4096

def init_telegram_sender(bot: Bot) -> None:
    global _bot
    _bot = bot

def _model_id(llm) -> str:
    return getattr(llm, "model", None) or getattr(llm, "model_name", None) or type(llm).__name__

async def on_startup():
    try:
        await get_tools()
    except Exception:
        logger.exception("Failed to initialize tools")
    try:
        await LLMInitializer.initialize()
    except Exception:
        logger.exception("Failed to initialize LLM")
    try:
        await get_checkpointer()
    except Exception:
        logger.exception("Failed to initialize checkpointer")
    logger.info("🤖 Assistant started")


async def on_shutdown():
    try:
        await close_calendar_client()
    except Exception:
        logger.exception("Failed to close calendar client")

    try:
        await close_reminders_client()
    except Exception:
        logger.exception("Failed to close reminders client")

    try:
        await close_checkpointer()
    except Exception:
        logger.exception("Failed to close checkpointer")

    logger.info("🤖 Assistant stopped")

async def send_message(tg_id: int, text: str) -> None:
    if _bot is None:
        raise RuntimeError("Telegram bot not initialized")

    await _bot.send_message(chat_id=tg_id, text=text[:MAX_MESSAGE_LEN], parse_mode=ParseMode.MARKDOWN)


def register_handlers(dp: Dispatcher):

    @dp.message(Command("switch_model"))
    async def handle_switch_model(message: Message):
        llms = LLMInitializer.get_llms()
        wrappers = LLMInitializer.get_wrappers()

        keyboard = [
            [InlineKeyboardButton(
                text=f"{_model_id(llm)} ({type(wrapper).__name__})",
                callback_data=f"switch_model:{_model_id(llm)}",
            )]
            for llm, wrapper in zip(llms, wrappers)
        ]

        await message.answer(
            text="Choose a model:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard),
        )

    @dp.callback_query(F.data.startswith("switch_model:"))
    async def handle_model_callback(callback: CallbackQuery):
        model_id = callback.data.split(":", 1)[1]
        tg_id = callback.from_user.id

        target_llm = next(
            (llm for llm in LLMInitializer.get_llms() if _model_id(llm) == model_id),
            None,
        )

        if target_llm is None:
            await callback.answer("⚠️ Model not found", show_alert=True)
            return

        LLMInitializer.set_selected(target_llm)
        AgentsFactory.reset(tg_id=tg_id) 

        await callback.answer(f"✅ Model switched: {model_id}")

    @dp.message(F.text)
    async def handle_text(message: Message):
        tg_id = message.from_user.id
        chat_id = message.chat.id
        text = message.text.strip()
        cfg = get_config()

        try:
            agent = await get_agent(tg_id)
            invoker = AgentInvoker(agent, tg_id)
            llm = LLMInitializer.get_selected()

            response = await invoker.invoke(
                user_message=text,
                runnable_config=cfg.RUNNABLE_CONFIG,
                llm=llm,
            )
            await send_message(chat_id, response)

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