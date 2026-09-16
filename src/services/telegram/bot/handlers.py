import json

from loguru import logger
from aiogram.filters import Command
from aiogram import Bot, Dispatcher, F
from aiogram.enums import ContentType, ParseMode
from aiogram.exceptions import TelegramAPIError
from aiogram.types import CallbackQuery, Message, InlineKeyboardButton, InlineKeyboardMarkup

from src.agents.chat import AgentInvoker
from src.factories.tools_factory import get_tools
from src.factories.agents_factory import AgentsFactory
from src.agents.llms.initializer import LLMInitializer
from src.services.dependencies import get_agent, get_user_model
from src.services.model_profiles import ModelProfileService
from src.services.models.providers import ModelProvider
from db.database import global_db_manager
from src.factories.checkpointer_factory import get_checkpointer, close_checkpointer
from src.agents.tools.reminders import close_reminders_client
from src.agents.tools.calendar import close_calendar_client

from data import get_config
from src.services.web.one_time_code import (
    LOGIN_CODE_COOLDOWN,
    LOGIN_CODE_TTL,
    generate_login_code,
    login_code_key,
)

_bot: Bot | None = None
MAX_MESSAGE_LEN = 4096

def init_telegram_sender(bot: Bot) -> None:
    global _bot
    _bot = bot

def _model_id(llm) -> str:
    return getattr(llm, "model", None) or getattr(llm, "model_name", None) or type(llm).__name__


def _model_setup_key(tg_id: int) -> str:
    return f"model_setup:{tg_id}"


async def _model_profiles(tg_id: int):
    async with global_db_manager.transaction() as session:
        service = ModelProfileService(
            global_db_manager.get_model_profiles_repo(session)
        )
        return await service.list(tg_id)


async def _model_keyboard(tg_id: int) -> InlineKeyboardMarkup:
    profiles = await _model_profiles(tg_id)
    rows = [
        [
            InlineKeyboardButton(
                text=f"{profile.display_name}{' ✅' if profile.is_active else ''}",
                callback_data=f"model:activate:{profile.id}",
            ),
            InlineKeyboardButton(
                text="Удалить",
                callback_data=f"model:delete:{profile.id}",
            ),
        ]
        for profile in profiles
    ]
    rows.extend(
        [
            [InlineKeyboardButton(text="➕ OpenAI", callback_data="model:add:openai")],
            [InlineKeyboardButton(text="➕ xAI", callback_data="model:add:xai")],
            [InlineKeyboardButton(text="🆓 Ollama разработчика", callback_data="model:add:ollama")],
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _send_models(message: Message) -> None:
    profiles = await _model_profiles(message.from_user.id)
    text = (
        "🤖 <b>Мои модели</b>\n\n"
        "Выберите активную модель или добавьте новую.\n"
        "OpenAI и xAI используют ваш API-ключ. Ollama разработчика доступна бесплатно."
    )
    if profiles:
        text += "\n\n" + "\n".join(
            f"• {profile.display_name}"
            f"{' — активна' if profile.is_active else ''}"
            for profile in profiles
        )
    await message.answer(text, reply_markup=await _model_keyboard(message.from_user.id))

async def on_startup():
    try:
        await get_tools()
    except (OSError, RuntimeError, ValueError):
        logger.exception("Failed to initialize tools")
    try:
        await LLMInitializer.initialize()
    except (OSError, RuntimeError, ValueError):
        logger.exception("Failed to initialize LLM")
    try:
        await get_checkpointer()
    except (OSError, RuntimeError, ValueError):
        logger.exception("Failed to initialize checkpointer")
    logger.info("🤖 Assistant started")


async def on_shutdown():
    try:
        await close_calendar_client()
    except (OSError, RuntimeError, ValueError):
        logger.exception("Failed to close calendar client")

    try:
        await close_reminders_client()
    except (OSError, RuntimeError, ValueError):
        logger.exception("Failed to close reminders client")

    try:
        await close_checkpointer()
    except (OSError, RuntimeError, ValueError):
        logger.exception("Failed to close checkpointer")

    logger.info("🤖 Assistant stopped")

async def send_message(tg_id: int, text: str) -> None:
    if _bot is None:
        raise RuntimeError("Telegram bot not initialized")

    await _bot.send_message(chat_id=tg_id, text=text[:MAX_MESSAGE_LEN], parse_mode=ParseMode.MARKDOWN)


def register_handlers(dp: Dispatcher):

    @dp.message(Command("web"))
    async def handle_web_login(message: Message):
        code = generate_login_code()
        redis = get_config().redis_client
        cooldown_key = f"web_login_cooldown:{message.from_user.id}"
        if not await redis.set(cooldown_key, "1", ex=LOGIN_CODE_COOLDOWN, nx=True):
            await message.answer("Код уже отправлен. Подождите минуту.")
            return
        await redis.setex(login_code_key(code), LOGIN_CODE_TTL, str(message.from_user.id))
        await message.answer(
            "Код для входа в Web UI: "
            f"{code}\nКод действителен 5 минут и одноразовый."
        )

    @dp.message(Command("models"))
    async def handle_models(message: Message):
        await _send_models(message)

    @dp.callback_query(F.data.startswith("model:add:"))
    async def handle_model_add(callback: CallbackQuery):
        provider = callback.data.rsplit(":", 1)[1]
        await get_config().redis_client.setex(
            _model_setup_key(callback.from_user.id),
            600,
            json.dumps({"provider": provider, "step": "model"}),
        )
        labels = {
            "openai": "OpenAI",
            "xai": "xAI",
            "ollama": "Ollama разработчика",
        }
        await callback.message.answer(
            f"Добавляем {labels.get(provider, provider)}.\n"
            "Напишите точное имя модели (например: gpt-4o-mini, grok-3-mini или llama3.2).\n"
            "Для отмены напишите /cancel."
        )
        await callback.answer()

    @dp.callback_query(F.data.startswith("model:activate:"))
    async def handle_model_activate(callback: CallbackQuery):
        profile_id = int(callback.data.rsplit(":", 1)[1])
        async with global_db_manager.transaction() as session:
            service = ModelProfileService(
                global_db_manager.get_model_profiles_repo(session)
            )
            profile = await service.activate(callback.from_user.id, profile_id)
        AgentsFactory.reset(tg_id=callback.from_user.id)
        await callback.message.edit_reply_markup(
            reply_markup=await _model_keyboard(callback.from_user.id)
        )
        await callback.answer(f"Активна: {profile.display_name}")

    @dp.callback_query(F.data.startswith("model:delete:"))
    async def handle_model_delete(callback: CallbackQuery):
        profile_id = int(callback.data.rsplit(":", 1)[1])
        async with global_db_manager.transaction() as session:
            service = ModelProfileService(
                global_db_manager.get_model_profiles_repo(session)
            )
            deleted = await service.delete(callback.from_user.id, profile_id)
        if deleted:
            AgentsFactory.reset(tg_id=callback.from_user.id)
        await callback.message.edit_reply_markup(
            reply_markup=await _model_keyboard(callback.from_user.id)
        )
        await callback.answer("Модель удалена" if deleted else "Модель не найдена")

    @dp.message(Command("cancel"))
    async def handle_model_cancel(message: Message):
        await get_config().redis_client.delete(_model_setup_key(message.from_user.id))
        await message.answer("Настройка модели отменена.")

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
        await callback.message.edit_text(f"Model switched to: {model_id}")

    @dp.message(F.text)
    async def handle_text(message: Message):
        tg_id = message.from_user.id
        chat_id = message.chat.id
        text = message.text.strip()
        cfg = get_config()

        try:
            setup_raw = await cfg.redis_client.get(_model_setup_key(tg_id))
            if setup_raw:
                setup = json.loads(setup_raw)
                if setup["step"] == "model":
                    setup["model_name"] = text
                    if setup["provider"] == "ollama":
                        async with global_db_manager.transaction() as session:
                            service = ModelProfileService(
                                global_db_manager.get_model_profiles_repo(session)
                            )
                            profile = await service.add(
                                tg_id,
                                ModelProvider.OLLAMA,
                                text,
                                text,
                            )
                            await service.activate(tg_id, profile.id)
                        await cfg.redis_client.delete(_model_setup_key(tg_id))
                        await message.answer(f"✅ Ollama-модель {text} добавлена и активирована.")
                    else:
                        setup["step"] = "api_key"
                        await cfg.redis_client.setex(
                            _model_setup_key(tg_id), 600, json.dumps(setup)
                        )
                        await message.answer(
                            "Теперь отправьте API-ключ одним сообщением.\n"
                            "Он не будет показан обратно и сохранится в зашифрованном виде."
                        )
                    return
                if setup["step"] == "api_key":
                    provider = ModelProvider(setup["provider"])
                    async with global_db_manager.transaction() as session:
                        service = ModelProfileService(
                            global_db_manager.get_model_profiles_repo(session)
                        )
                        profile = await service.add(
                            tg_id,
                            provider,
                            setup["model_name"],
                            setup["model_name"],
                            text,
                        )
                        await service.activate(tg_id, profile.id)
                    await cfg.redis_client.delete(_model_setup_key(tg_id))
                    try:
                        await message.delete()
                    except TelegramAPIError:
                        logger.debug("Could not delete model API key message")
                    await message.answer(
                        f"✅ {provider.value} модель {setup['model_name']} добавлена и активирована."
                    )
                    return
            agent = await get_agent(tg_id)
            invoker = AgentInvoker(agent, tg_id)
            llm = await get_user_model(tg_id) or LLMInitializer.get_selected()

            response = await invoker.invoke(
                user_message=text,
                runnable_config=cfg.RUNNABLE_CONFIG,
                llm=llm,
            )
            await send_message(chat_id, response)

        except (OSError, RuntimeError, ValueError) as e:
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