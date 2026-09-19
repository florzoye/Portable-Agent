import json
import os

from loguru import logger
from aiogram.filters import Command
from aiogram import Bot, Dispatcher, F
from aiogram.enums import ContentType, ParseMode
from aiogram.exceptions import TelegramAPIError
from aiogram.types import (
    CallbackQuery,
    Message,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardRemove,
    ReplyKeyboardMarkup,
    KeyboardButton,
)
from aiogram.fsm.context import FSMContext

from src.agents.chat import AgentInvoker
from src.factories.tools_factory import get_tools
from src.factories.agents_factory import AgentsFactory
from src.agents.llms.initializer import LLMInitializer
from src.agents.providers.base import (
    ProviderConfigurationError,
    provider_user_message,
)
from src.services.dependencies import (
    NoActiveModelError,
    get_agent_for_model,
    resolve_model,
)
from src.services.models.providers import ModelProvider
from src.services.dependencies import get_model_profiles
from src.services.telegram.model_setup_guidance import (
    ModelSetupIntent,
    detect_model_setup_request,
    format_provider_help,
    setup_help_text,
)
from src.services.telegram.bot.states import TelegramMode
from src.factories.checkpointer_factory import get_checkpointer, close_checkpointer
from src.agents.tools.reminders import close_reminders_client
from src.agents.tools.calendar import close_calendar_client

from data import get_config
from src.services.web.one_time_code import (
    LOGIN_CODE_COOLDOWN,
    LOGIN_CODE_TTL,
    generate_login_code,
    generate_login_token,
    login_code_key,
    login_token_key,
)

_bot: Bot | None = None
MAX_MESSAGE_LEN = 4096
EXIT_CHAT_TEXT = "⏹ Выйти из чата"

def init_telegram_sender(bot: Bot) -> None:
    global _bot
    _bot = bot

def _model_id(llm) -> str:
    return getattr(llm, "model", None) or getattr(llm, "model_name", None) or type(llm).__name__


def _model_setup_key(tg_id: int) -> str:
    return f"model_setup:{tg_id}"


def _current_login_code_key(tg_id: int) -> str:
    """Redis key holding the *one* code currently valid for this user,
    so a freshly issued code can invalidate whatever came before it."""
    return f"web_login_current_code:{tg_id}"


def _current_login_token_key(tg_id: int) -> str:
    return f"web_login_current_token:{tg_id}"

def _setup_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⬅️ Назад к моделям",
                    callback_data="model:back",
                ),
                InlineKeyboardButton(
                    text="❌ Отмена",
                    callback_data="model:cancel",
                ),
            ]
        ]
    )


def _guided_setup_keyboard(
    provider: str | None = None,
) -> InlineKeyboardMarkup:
    if provider is None:
        providers = tuple(
            capability.provider.value
            for capability in get_model_profiles().available_providers()
        )
    else:
        providers = (provider,)
    return InlineKeyboardMarkup(
        inline_keyboard=[
            *[
                [
                    InlineKeyboardButton(
                        text=f"Начать настройку {candidate}",
                        callback_data=f"guided:model:start:{candidate}",
                    )
                ]
                for candidate in providers
            ],
            [
                InlineKeyboardButton(text="Список провайдеров", callback_data="guided:model:providers"),
                InlineKeyboardButton(text="❌ Отмена", callback_data="nav:cancel"),
            ],
        ]
    )


def _menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💬 Открыть чат", callback_data="menu:chat")],
            [InlineKeyboardButton(text="🤖 Мои модели", callback_data="menu:models")],
            [InlineKeyboardButton(text="🌐 Войти в Web UI", callback_data="menu:web")],
            [InlineKeyboardButton(text="ℹ️ Помощь", callback_data="menu:help")],
        ]
    )



def _chat_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=EXIT_CHAT_TEXT)]],
        resize_keyboard=True,
        is_persistent=True,
    )

def _back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ В меню", callback_data="menu:back")]
        ]
    )


def _setup_prompt(provider: str, step: str) -> str:
    labels = {
        "openai": "OpenAI",
        "xai": "xAI",
        "ollama": "Ollama разработчика",
    }
    if step == "api_key":
        return (
            f"Шаг 2/2: отправьте API-ключ для {labels.get(provider, provider)}.\n"
            "Ключ не будет показан обратно и сохранится в зашифрованном виде."
        )
    return (
        f"Шаг 1/2: настройка {labels.get(provider, provider)}.\n"
        "Напишите точное имя модели.\n"
        "Для возврата нажмите «Назад», для отмены — «Отмена»."
    )


async def _model_profiles(tg_id: int):
    return await get_model_profiles().list(tg_id)


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
            [InlineKeyboardButton(text="⬅️ В меню", callback_data="menu:back")],
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _send_models(message: Message, user_id: int | None = None) -> None:
    tg_id = user_id if user_id is not None else message.from_user.id
    profiles = await _model_profiles(tg_id)
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
    await message.answer(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=await _model_keyboard(tg_id),
    )


def _profile_id_from_callback(callback_data: str) -> int | None:
    try:
        value = callback_data.rsplit(":", 1)[1]
        profile_id = int(value)
    except (IndexError, TypeError, ValueError):
        return None
    return profile_id if profile_id > 0 else None

async def on_startup():
    from db.database import global_db_manager

    await global_db_manager.setup()
    await global_db_manager.create_tables()
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
    from db.database import global_db_manager

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
    await global_db_manager.close()

    logger.info("🤖 Assistant stopped")

async def send_message(tg_id: int, text: str) -> None:
    if _bot is None:
        raise RuntimeError("Telegram bot not initialized")

    await _bot.send_message(chat_id=tg_id, text=text[:MAX_MESSAGE_LEN], parse_mode=ParseMode.MARKDOWN)


def register_handlers(dp: Dispatcher):

    @dp.callback_query.outer_middleware()
    async def callback_owner_guard(handler, event, data):
        callback = event
        message = callback.message
        if (
            message is None
            or message.chat.type != "private"
            or callback.from_user.id != message.chat.id
        ):
            await callback.answer(
                "Это меню доступно только владельцу чата.",
                show_alert=True,
            )
            return
        return await handler(event, data)

    async def show_menu(message: Message, state: FSMContext, *, edit: bool = False):
        await state.set_state(TelegramMode.navigation)
        text = (
            "🏠 <b>PortableAgent</b>\n\n"
            "Выберите действие. Календарь и напоминания доступны обычным текстом "
            "в режиме чата."
        )
        if edit:
            await message.edit_text(text, reply_markup=_menu_keyboard())
        else:
            await message.answer(text, reply_markup=_menu_keyboard())

    async def enter_chat(message: Message, state: FSMContext):
        await get_config().redis_client.delete(_model_setup_key(message.from_user.id))
        await state.set_state(TelegramMode.chat)
        await message.answer(
            "💬 <b>Режим чата включён</b>\n\n"
            "Пишите обычным языком: я помогу с вопросами, календарём и напоминаниями.\n"
            "Для выхода нажмите кнопку ниже или используйте /cancel.",
            reply_markup=_chat_keyboard(),
        )

    async def leave_chat(message: Message, state: FSMContext, *, edit: bool = False):
        await state.set_state(TelegramMode.navigation)
        if edit:
            await message.edit_text("Вы вышли из чата.", reply_markup=_menu_keyboard())
        else:
            await message.answer(
                "Вы вышли из чата.",
                reply_markup=ReplyKeyboardRemove(),
            )
            await message.answer(
                "Открываю меню.",
                reply_markup=_menu_keyboard(),
            )

    @dp.message(Command("start"))
    async def handle_start(message: Message, state: FSMContext):
        await show_menu(message, state)

    @dp.message(Command("menu"))
    async def handle_menu(message: Message, state: FSMContext):
        await show_menu(message, state)

    @dp.message(Command("chat"))
    async def handle_chat(message: Message, state: FSMContext):
        await enter_chat(message, state)

    @dp.message(Command("calendar"))
    async def handle_calendar_alias(message: Message, state: FSMContext):
        await enter_chat(message, state)
        await message.answer(
            "Календарь работает через обычный язык. Например: "
            "«покажи мои события на сегодня»."
        )

    @dp.message(Command("reminders"))
    async def handle_reminders_alias(message: Message, state: FSMContext):
        await enter_chat(message, state)
        await message.answer(
            "Напоминания работают через обычный язык. Например: "
            "«напомни завтра в 10:00 позвонить врачу»."
        )

    @dp.message(Command("cancel"))
    async def handle_cancel(message: Message, state: FSMContext):
        await get_config().redis_client.delete(_model_setup_key(message.from_user.id))
        current_state = await state.get_state()
        if current_state == TelegramMode.chat.state:
            await leave_chat(message, state)
            return
        await state.set_state(TelegramMode.navigation)
        await message.answer("Текущее действие отменено.", reply_markup=_menu_keyboard())

    @dp.message(Command("web"))
    async def handle_web_login(
        message: Message,
        state: FSMContext,
        user_id: int | None = None,
    ):
        await state.set_state(TelegramMode.navigation)
        tg_id = user_id if user_id is not None else message.from_user.id
        redis = get_config().redis_client
        cooldown_key = f"web_login_cooldown:{tg_id}"
        if not await redis.set(cooldown_key, "1", ex=LOGIN_CODE_COOLDOWN, nx=True):
            await message.answer("Ссылка уже отправлена. Подождите минуту.")
            return

        code = generate_login_code()
        token = generate_login_token()

        current_code_key = _current_login_code_key(tg_id)
        previous_code = await redis.getdel(current_code_key)
        if previous_code:
            await redis.delete(login_code_key(previous_code))
        current_token_key = _current_login_token_key(tg_id)
        previous_token = await redis.getdel(current_token_key)
        if previous_token:
            await redis.delete(login_token_key(previous_token))

        await redis.setex(login_code_key(code), LOGIN_CODE_TTL, str(tg_id))
        await redis.setex(current_code_key, LOGIN_CODE_TTL, code)
        web_url = os.environ.get("WEB_PUBLIC_URL", "").rstrip("/")
        if not web_url:
            await message.answer(
                "Web UI временно не настроен: администратор должен задать WEB_PUBLIC_URL."
            )
            return
        await redis.setex(login_token_key(token), LOGIN_CODE_TTL, str(tg_id))
        await redis.setex(current_token_key, LOGIN_CODE_TTL, token)
        await message.answer(
            "Откройте Web UI по одноразовой ссылке. "
            "Ссылка действительна 5 минут и работает только один раз.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="🌐 Открыть Web UI", url=f"{web_url}/auth/link?token={token}")],
                    [InlineKeyboardButton(text="⬅️ В меню", callback_data="menu:back")],
                ]
            ),
        )

    @dp.message(Command("models"))
    async def handle_models(message: Message, state: FSMContext):
        await state.set_state(TelegramMode.navigation)
        await _send_models(message)

    @dp.message(Command("help"))
    async def handle_help(message: Message, state: FSMContext):
        await state.set_state(TelegramMode.navigation)
        await message.answer(
            "ℹ️ <b>Как пользоваться</b>\n\n"
            "Войдите в чат командой /chat и пишите обычным языком.\n"
            "Примеры:\n"
            "• «Что у меня сегодня в календаре?»\n"
            "• «Напомни завтра в 10:00 позвонить врачу»\n"
            "• «Перенеси встречу с Анной на пятницу»\n\n"
            "Для выхода используйте /cancel.",
            reply_markup=_back_keyboard(),
        )

    @dp.callback_query(F.data == "menu:chat")
    async def handle_chat_callback(callback: CallbackQuery, state: FSMContext):
        await callback.answer()
        await enter_chat(callback.message, state)

    @dp.callback_query(F.data == "menu:models")
    async def handle_models_callback(callback: CallbackQuery, state: FSMContext):
        await state.set_state(TelegramMode.navigation)
        await callback.answer()
        await _send_models(callback.message, callback.from_user.id)

    @dp.callback_query(F.data == "menu:web")
    async def handle_web_callback(callback: CallbackQuery, state: FSMContext):
        await state.set_state(TelegramMode.navigation)
        await callback.answer()
        await handle_web_login(callback.message, state, callback.from_user.id)

    @dp.callback_query(F.data == "menu:help")
    async def handle_help_callback(callback: CallbackQuery, state: FSMContext):
        await state.set_state(TelegramMode.navigation)
        await callback.answer()
        await handle_help(callback.message, state)

    @dp.callback_query(F.data == "menu:back")
    async def handle_menu_back(callback: CallbackQuery, state: FSMContext):
        await callback.answer()
        await show_menu(callback.message, state, edit=True)

    @dp.callback_query(F.data == "guided:model:providers")
    async def handle_guided_providers(callback: CallbackQuery):
        capabilities = get_model_profiles().available_providers()
        await callback.message.edit_text(
            format_provider_help(capabilities),
            reply_markup=_guided_setup_keyboard(),
        )
        await callback.answer()

    @dp.callback_query(F.data.startswith("guided:model:start:"))
    async def handle_guided_setup_start(callback: CallbackQuery):
        provider = callback.data.rsplit(":", 1)[1]
        available = {
            capability.provider.value
            for capability in get_model_profiles().available_providers()
        }
        if provider not in available:
            await callback.answer("Провайдер больше недоступен.", show_alert=True)
            return
        await callback.message.edit_text(
            _setup_prompt(provider, "model"),
            reply_markup=_setup_keyboard(),
        )
        await get_config().redis_client.setex(
            _model_setup_key(callback.from_user.id),
            600,
            json.dumps({"provider": provider, "step": "model"}),
        )
        await callback.answer()

    @dp.callback_query(F.data.startswith("model:add:"))
    async def handle_model_add(callback: CallbackQuery):
        provider = callback.data.rsplit(":", 1)[1]
        await get_config().redis_client.setex(
            _model_setup_key(callback.from_user.id),
            600,
            json.dumps({"provider": provider, "step": "model"}),
        )
        await callback.message.answer(
            _setup_prompt(provider, "model"),
            reply_markup=_setup_keyboard(),
        )
        await callback.answer()

    @dp.callback_query(F.data == "model:cancel")
    async def handle_model_cancel_callback(callback: CallbackQuery):
        await get_config().redis_client.delete(
            _model_setup_key(callback.from_user.id)
        )
        await callback.message.edit_text("Настройка модели отменена.")
        await callback.answer()

    @dp.callback_query(F.data == "model:back")
    async def handle_model_back(callback: CallbackQuery):
        await get_config().redis_client.delete(
            _model_setup_key(callback.from_user.id)
        )
        await callback.message.answer(
            "Выберите действие в разделе моделей.",
            reply_markup=await _model_keyboard(callback.from_user.id),
        )
        await callback.answer()

    @dp.callback_query(F.data.startswith("model:activate:"))
    async def handle_model_activate(callback: CallbackQuery):
        profile_id = _profile_id_from_callback(callback.data)
        if profile_id is None:
            await callback.answer("Некорректная кнопка. Откройте список моделей заново.", show_alert=True)
            await callback.message.edit_reply_markup(
                reply_markup=await _model_keyboard(callback.from_user.id)
            )
            return
        try:
            profile = await get_model_profiles().activate(
                callback.from_user.id, profile_id
            )
        except (ValueError, RuntimeError):
            await callback.answer("Модель больше недоступна. Обновите список.", show_alert=True)
            await callback.message.edit_reply_markup(
                reply_markup=await _model_keyboard(callback.from_user.id)
            )
            return
        AgentsFactory.reset(tg_id=callback.from_user.id)
        await callback.message.edit_reply_markup(
            reply_markup=await _model_keyboard(callback.from_user.id)
        )
        await callback.answer(f"Активна: {profile.display_name}")

    @dp.callback_query(F.data.startswith("model:delete:"))
    async def handle_model_delete(callback: CallbackQuery):
        profile_id = _profile_id_from_callback(callback.data)
        if profile_id is None:
            await callback.answer("Некорректная кнопка. Откройте список моделей заново.", show_alert=True)
            await callback.message.edit_reply_markup(
                reply_markup=await _model_keyboard(callback.from_user.id)
            )
            return
        try:
            deleted = await get_model_profiles().delete(
                callback.from_user.id, profile_id
            )
        except (ValueError, RuntimeError):
            await callback.answer("Модель больше недоступна. Обновите список.", show_alert=True)
            await callback.message.edit_reply_markup(
                reply_markup=await _model_keyboard(callback.from_user.id)
            )
            return
        if deleted:
            AgentsFactory.reset(tg_id=callback.from_user.id)
        await callback.message.edit_reply_markup(
            reply_markup=await _model_keyboard(callback.from_user.id)
        )
        await callback.answer("Модель удалена" if deleted else "Модель не найдена")

    @dp.message(F.text)
    async def handle_text(message: Message, state: FSMContext):
        tg_id = message.from_user.id
        chat_id = message.chat.id
        text = message.text.strip()
        cfg = get_config()

        if text == EXIT_CHAT_TEXT and await state.get_state() == TelegramMode.chat.state:
            await leave_chat(message, state)
            return

        if await state.get_state() != TelegramMode.chat.state:
            setup_raw = await cfg.redis_client.get(_model_setup_key(tg_id))
            if not setup_raw:
                await message.answer(
                    "Чтобы начать разговор, используйте /chat.",
                    reply_markup=_menu_keyboard(),
                )
                return

        try:
            guided_request = detect_model_setup_request(text)
            if guided_request is not None:
                if guided_request.intent is ModelSetupIntent.LIST_PROVIDERS:
                    await message.answer(
                        format_provider_help(get_model_profiles().available_providers()),
                        reply_markup=_guided_setup_keyboard(),
                    )
                    return
                if guided_request.intent is ModelSetupIntent.SHOW_SETUP_HELP:
                    await message.answer(
                        setup_help_text(),
                        reply_markup=_guided_setup_keyboard(),
                    )
                    return
                await message.answer(
                    "Запуск настройки требует подтверждения. "
                    "Выберите провайдера ниже.",
                    reply_markup=_guided_setup_keyboard(guided_request.provider),
                )
                return

            setup_raw = await cfg.redis_client.get(_model_setup_key(tg_id))
            if setup_raw:
                setup = json.loads(setup_raw)
                if setup["step"] == "model":
                    setup["model_name"] = text
                    if setup["provider"] == "ollama":
                        try:
                            profile = await get_model_profiles().add(
                                tg_id, ModelProvider.OLLAMA, text, text
                            )
                            await get_model_profiles().activate(tg_id, profile.id)
                        except (ProviderConfigurationError, ValueError, RuntimeError):
                            await message.answer(
                                "Не удалось добавить модель. Проверьте имя и попробуйте ещё раз.",
                                reply_markup=_setup_keyboard(),
                            )
                            return
                        await cfg.redis_client.delete(_model_setup_key(tg_id))
                        await message.answer(f"✅ Шаг 2/2 завершён: Ollama-модель {text} добавлена и активирована.")
                    else:
                        setup["step"] = "api_key"
                        await cfg.redis_client.setex(
                            _model_setup_key(tg_id), 600, json.dumps(setup)
                        )
                        await message.answer(
                            _setup_prompt(setup["provider"], "api_key"),
                            reply_markup=_setup_keyboard(),
                        )
                    return
                if setup["step"] == "api_key":
                    provider = ModelProvider(setup["provider"])
                    try:
                        profile = await get_model_profiles().add(
                            tg_id, provider, setup["model_name"], setup["model_name"], text
                        )
                        await get_model_profiles().activate(tg_id, profile.id)
                    except (ProviderConfigurationError, ValueError, RuntimeError):
                        try:
                            await message.delete()
                        except TelegramAPIError:
                            logger.debug("Could not delete failed model API key message")
                        await message.answer(
                            "Не удалось сохранить профиль. Проверьте API-ключ и попробуйте ещё раз.",
                            reply_markup=_setup_keyboard(),
                        )
                        return
                    await cfg.redis_client.delete(_model_setup_key(tg_id))
                    try:
                        await message.delete()
                    except TelegramAPIError:
                        logger.debug("Could not delete model API key message")
                    await message.answer(
                        f"✅ {provider.value} модель {setup['model_name']} добавлена и активирована."
                    )
                    return
            llm = await resolve_model(str(tg_id), tg_id)
            agent = await get_agent_for_model(str(tg_id), tg_id, llm)
            invoker = AgentInvoker(agent, tg_id)

            response = await invoker.invoke(
                user_message=text,
                runnable_config=cfg.RUNNABLE_CONFIG,
                llm=llm,
            )
            await send_message(chat_id, response)

        except NoActiveModelError:
            await message.answer(
                "Активная модель не выбрана. Настройте профиль модели через раздел «Модели»."
            )
        except (OSError, RuntimeError, ValueError) as error:
            logger.exception("Agent error for tg_id={}", tg_id)
            await message.answer(f"⚠️ {provider_user_message(error)}")

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