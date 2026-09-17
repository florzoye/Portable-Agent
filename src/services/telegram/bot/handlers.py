import json

from loguru import logger
from aiogram.filters import Command
from aiogram import Bot, Dispatcher, F
from aiogram.enums import ContentType, ParseMode
from aiogram.exceptions import TelegramAPIError
from aiogram.types import (
    CallbackQuery,
    KeyboardButton,
    Message,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
)

from src.agents.chat import AgentInvoker
from src.factories.tools_factory import get_tools
from src.factories.agents_factory import AgentsFactory
from src.agents.llms.initializer import LLMInitializer
from src.agents.providers.base import provider_user_message
from src.services.dependencies import (
    NoActiveModelError,
    get_agent,
    get_user_model,
)
from src.services.models.providers import ModelProvider
from src.services.dependencies import get_model_profiles
from src.services.telegram.model_setup_guidance import (
    ModelSetupIntent,
    detect_model_setup_request,
    format_provider_help,
    setup_help_text,
)
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


def _main_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="💬 Чат"), KeyboardButton(text="🤖 Модели")],
            [KeyboardButton(text="📅 Календарь"), KeyboardButton(text="⏰ Напоминания")],
            [KeyboardButton(text="ℹ️ Помощь"), KeyboardButton(text="⚙️ Настройки")],
            [KeyboardButton(text="❌ Отмена")],
        ],
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="Выберите действие или напишите сообщение",
    )


def _section_keyboard(section: str) -> InlineKeyboardMarkup:
    if section == "calendar":
        rows = [
            [InlineKeyboardButton(text="➕ Создать событие", callback_data="nav:calendar:create")],
            [InlineKeyboardButton(text="📋 Мои события", callback_data="nav:calendar:list")],
        ]
    else:
        rows = [
            [InlineKeyboardButton(text="➕ Создать напоминание", callback_data="nav:reminders:create")],
            [InlineKeyboardButton(text="📋 Мои напоминания", callback_data="nav:reminders:list")],
        ]
    rows.append(
        [
            InlineKeyboardButton(text="⬅️ Назад", callback_data="nav:back"),
            InlineKeyboardButton(text="❌ Отмена", callback_data="nav:cancel"),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


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

    @dp.message(Command("start"))
    async def handle_start(message: Message):
        await message.answer(
            "Добро пожаловать! Выберите раздел или напишите сообщение.",
            reply_markup=_main_keyboard(),
        )

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

    @dp.message(F.text == "🤖 Модели")
    async def handle_models_button(message: Message):
        await _send_models(message)

    @dp.message(F.text == "💬 Чат")
    async def handle_chat_button(message: Message):
        await message.answer(
            "Режим чата включён. Напишите сообщение.",
            reply_markup=_main_keyboard(),
        )

    @dp.message(F.text == "📅 Календарь")
    async def handle_calendar_button(message: Message):
        await message.answer(
            "Выберите действие календаря:",
            reply_markup=_section_keyboard("calendar"),
        )

    @dp.message(F.text == "⏰ Напоминания")
    async def handle_reminders_button(message: Message):
        await message.answer(
            "Выберите действие с напоминаниями:",
            reply_markup=_section_keyboard("reminders"),
        )

    @dp.callback_query(F.data.startswith("nav:calendar:"))
    async def handle_calendar_navigation(callback: CallbackQuery):
        action = callback.data.rsplit(":", 1)[1]
        prompts = {
            "create": "Опишите событие: например, «создай встречу завтра в 10:00»",
            "list": "Напишите, какие события показать: например, «покажи мои события на сегодня»",
        }
        await callback.message.edit_text(
            prompts.get(action, "Выберите действие календаря."),
            reply_markup=_section_keyboard("calendar"),
        )
        await callback.answer()

    @dp.callback_query(F.data.startswith("nav:reminders:"))
    async def handle_reminders_navigation(callback: CallbackQuery):
        action = callback.data.rsplit(":", 1)[1]
        prompts = {
            "create": "Опишите напоминание: например, «напомни позвонить через час»",
            "list": "Напишите, какие напоминания показать: например, «покажи активные напоминания»",
        }
        await callback.message.edit_text(
            prompts.get(action, "Выберите действие с напоминаниями."),
            reply_markup=_section_keyboard("reminders"),
        )
        await callback.answer()

    @dp.callback_query(F.data == "nav:back")
    async def handle_navigation_back(callback: CallbackQuery):
        await callback.message.answer(
            "Выберите раздел.",
            reply_markup=_main_keyboard(),
        )
        await callback.answer()

    @dp.callback_query(F.data == "nav:cancel")
    async def handle_navigation_cancel(callback: CallbackQuery):
        await callback.message.edit_text("Раздел закрыт.")
        await callback.answer()

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

    @dp.message(F.text == "ℹ️ Помощь")
    async def handle_help_button(message: Message):
        await message.answer(
            "Напишите запрос обычным текстом. В разделе «Модели» можно "
            "добавить или активировать профиль. /web открывает Web UI.",
            reply_markup=_main_keyboard(),
        )

    @dp.message(F.text == "⚙️ Настройки")
    async def handle_settings_button(message: Message):
        await message.answer(
            "Настройки модели находятся в разделе «Модели». "
            "Для входа в Web UI используйте /web.",
            reply_markup=_main_keyboard(),
        )

    @dp.message(F.text == "❌ Отмена")
    async def handle_cancel_button(message: Message):
        await get_config().redis_client.delete(_model_setup_key(message.from_user.id))
        await message.answer(
            "Текущая операция отменена.",
            reply_markup=_main_keyboard(),
        )

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
        profile_id = int(callback.data.rsplit(":", 1)[1])
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
        profile_id = int(callback.data.rsplit(":", 1)[1])
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
            agent = await get_agent(tg_id)
            invoker = AgentInvoker(agent, tg_id)
            llm = await get_user_model(tg_id)
            if llm is None:
                raise NoActiveModelError(
                    "Сначала создайте или активируйте профиль модели"
                )

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