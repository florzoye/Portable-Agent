import json
import os
import tempfile
import unittest
from unittest.mock import AsyncMock, patch
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy import insert

from fastapi import HTTPException, Response

from src.agents.memory import normalize_memory_user_id, user_memory_path
from src.services.calendar.mcp.common import event_list_result, event_result
from src.services.tool_result import tool_failure, tool_success
from src.services.web.app import (
    _acquire_provider_diagnostic_slot,
    activate_model_profile,
    code_login,
    CodeLoginRequest,
    current_user,
    link_login,
    delete_model_profile,
    list_model_profiles,
    current_model,
    _get_session_context,
    _selected_web_conversation,
)
from src.services.telegram.bot.handlers import (
    _profile_id_from_callback,
    _setup_keyboard,
    _setup_prompt,
)
from src.services.web.one_time_code import (
    generate_login_code,
    login_token_key,
    normalize_login_code,
)
from utils.observability import emit_event, timed_event
from utils.token_usage import extract_token_usage
from src.services.model_profiles import ModelProfileApplication, ModelProfileService
from src.services.models.providers import (
    ModelProvider,
    ProviderCapabilities,
    UserModelProfile,
)
from src.agents.providers.base import (
    ProviderRequestError,
    ProviderTimeoutError,
    provider_user_message,
)
from src.agents.providers.factory import UserModelFactory
from src.agents.providers.base import ProviderAdapter, ProviderContext
from src.agents.providers.adapters import OpenAIProvider
from src.services.dependencies import (
    NoActiveModelError,
    get_agent_for_model,
    get_session_model,
    resolve_model,
)
from src.services.telegram.bot.handlers import on_startup, on_shutdown


class FakeRedis:
    def __init__(self, values=None):
        self.values = values or {}
        self.expired = []

    async def get(self, key):
        return self.values.get(key)

    async def expire(self, key, ttl):
        self.expired.append((key, ttl))

    async def set(self, key, value, ex=None, nx=False):
        if nx and key in self.values:
            return False
        self.values[key] = value
        self.expired.append((key, ex))
        return True


class ComprehensiveTests(unittest.IsolatedAsyncioTestCase):
    async def test_web_login_cookie_is_available_to_all_routes(self):
        class LoginRedis(FakeRedis):
            def __init__(self):
                super().__init__({"web_login_code:12345678": "1694304302"})
                self.attempts = 0

            async def incr(self, key):
                self.attempts += 1
                return self.attempts

            async def setex(self, key, ttl, value):
                self.values[key] = value

            async def getdel(self, key):
                return self.values.pop(key, None)

        class Config:
            redis_client = LoginRedis()

        class Client:
            host = "test-client"

        class Request:
            client = Client()

        response = Response()
        with patch("src.services.web.app.get_config", return_value=Config()):
            result = await code_login(
                CodeLoginRequest(code="12345678"),
                Request(),
                response,
            )

        self.assertEqual(result, {"user_id": 1694304302})
        self.assertIn("portable_session=", response.headers["set-cookie"])
        self.assertIn("Path=/", response.headers["set-cookie"])

        session_id = next(
            key.removeprefix("web_session:")
            for key in Config.redis_client.values
            if key.startswith("web_session:")
        )
        with patch("src.services.web.app.get_config", return_value=Config()):
            current = await current_user(session_id)
        self.assertEqual(current, {"user_id": 1694304302})

    async def test_web_login_link_is_single_use_and_sets_session_cookie(self):
        class LinkRedis(FakeRedis):
            async def getdel(self, key):
                return self.values.pop(key, None)

            async def setex(self, key, ttl, value):
                self.values[key] = value

        class Config:
            redis_client = LinkRedis({login_token_key("token"): "1694304302"})

        with patch("src.services.web.app.get_config", return_value=Config()):
            response = await link_login("token")

        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers["location"], "/")
        self.assertIn("portable_session=", response.headers["set-cookie"])
        self.assertNotIn(login_token_key("token"), Config.redis_client.values)

    async def test_web_profile_transport_preserves_tenant_ownership(self):
        class ProfileApplication:
            def __init__(self):
                self.calls = []

            async def list(self, user_id):
                self.calls.append(("list", user_id))
                return [
                    UserModelProfile(
                        id=11,
                        user_id=user_id,
                        provider=ModelProvider.OLLAMA,
                        model_name="llama",
                        display_name="Tenant model",
                        is_active=True,
                    )
                ]

            async def activate(self, user_id, profile_id):
                self.calls.append(("activate", user_id, profile_id))
                raise ValueError("Model profile not found")

            async def delete(self, user_id, profile_id):
                self.calls.append(("delete", user_id, profile_id))
                return False

        application = ProfileApplication()
        with patch(
            "src.services.web.app._get_session_context",
            return_value=(101, "thread-101"),
        ), patch(
            "src.services.web.app.get_model_profiles",
            return_value=application,
        ):
            listed = await list_model_profiles("session-101")
            with self.assertRaises(HTTPException) as error:
                await activate_model_profile(999, "session-101")
            deleted = await delete_model_profile(999, "session-101")

        self.assertEqual(listed["profiles"][0]["id"], 11)
        self.assertEqual(error.exception.status_code, 404)
        self.assertEqual(deleted, {"deleted": False})
        self.assertEqual(
            application.calls,
            [
                ("list", 101),
                ("activate", 101, 999),
                ("delete", 101, 999),
            ],
        )

    async def test_authenticated_session_returns_server_owned_thread(self):
        redis = FakeRedis({
            "web_session:session": "42",
            "web_session_thread:session": "server-thread",
        })
        config = type("Config", (), {"redis_client": redis})()

        with patch("src.services.web.app.get_config", return_value=config):
            user_id, thread_id = await _get_session_context("session")

        self.assertEqual((user_id, thread_id), (42, "server-thread"))
        self.assertEqual(len(redis.expired), 2)

    async def test_profile_transport_uses_cookie_owned_tenant(self):
        redis = FakeRedis({
            "web_session:auth-session": "42",
            "web_session_thread:auth-session": "server-thread",
        })
        config = type("Config", (), {"redis_client": redis})()

        class ProfileApplication:
            def __init__(self):
                self.user_ids = []

            async def list(self, user_id):
                self.user_ids.append(user_id)
                return [
                    UserModelProfile(
                        id=11,
                        user_id=user_id,
                        provider=ModelProvider.OLLAMA,
                        model_name="llama",
                        display_name="Tenant model",
                        is_active=True,
                    )
                ]

        application = ProfileApplication()
        with patch("src.services.web.app.get_config", return_value=config), patch(
            "src.services.web.app.get_model_profiles",
            return_value=application,
        ):
            result = await list_model_profiles("auth-session")

        self.assertEqual(result["profiles"][0]["id"], 11)
        self.assertEqual(application.user_ids, [42])

    async def test_missing_session_is_rejected(self):
        redis = FakeRedis()
        config = type("Config", (), {"redis_client": redis})()

        with patch("src.services.web.app.get_config", return_value=config):
            with self.assertRaises(HTTPException) as error:
                await _get_session_context("missing")

        self.assertEqual(error.exception.status_code, 401)

    async def test_current_model_returns_empty_state_without_profile(self):
        with patch(
            "src.services.web.app._get_session_context",
            return_value=(42, "thread-42"),
        ), patch(
            "src.services.web.app.get_model_profiles"
        ) as profiles, patch(
            "src.services.web.app.get_user_model",
            return_value=None,
        ), patch(
            "src.services.web.app.get_session_model",
            return_value=None,
        ):
            profiles.return_value.list = AsyncMock(return_value=[])
            result = await current_model("session-42")

        self.assertEqual(result["status"], "no_active_profile")
        self.assertIsNone(result["active_model"])
        self.assertEqual(result["source"], "none")

    def test_session_model_returns_none_when_operator_fallback_disabled(self):
        with patch.dict(os.environ, {"ALLOW_OPERATOR_FALLBACK": "false"}, clear=False):
            with patch(
                "src.services.dependencies._session_models",
                {},
            ):
                self.assertIsNone(get_session_model("thread-42"))

    def test_agent_requires_model_when_fallback_disabled(self):
        self.assertTrue(issubclass(NoActiveModelError, RuntimeError))

    async def test_agent_for_resolved_model_initializes_dependencies(self):
        model = object()
        factory = type("Factory", (), {"aget_agent": AsyncMock(return_value="agent")})()
        with patch(
            "src.services.dependencies.get_checkpointer",
            new=AsyncMock(return_value="checkpointer"),
        ) as get_checkpointer, patch(
            "src.services.dependencies.get_tools",
            new=AsyncMock(return_value=["tool"]),
        ) as get_tools, patch(
            "src.services.dependencies.AgentsFactory",
            return_value=factory,
        ) as agents_factory:
            result = await get_agent_for_model("thread-42", 42, model)

        self.assertEqual(result, "agent")
        get_checkpointer.assert_awaited_once()
        get_tools.assert_awaited_once()
        agents_factory.assert_called_once()

    async def test_resolve_model_raises_domain_error_without_active_profile(self):
        with patch(
            "src.services.dependencies.get_user_model",
            new=AsyncMock(return_value=None),
        ), patch(
            "src.services.dependencies.get_session_model",
            return_value=None,
        ):
            with self.assertRaises(NoActiveModelError):
                await resolve_model("thread-42", 42)

    async def test_telegram_startup_initializes_database_before_handlers(self):
        database = type(
            "Database",
            (),
            {
                "setup": AsyncMock(),
                "create_tables": AsyncMock(),
                "close": AsyncMock(),
            },
        )()
        with patch(
            "db.database.global_db_manager",
            database,
        ), patch(
            "src.services.telegram.bot.handlers.get_tools",
            new=AsyncMock(),
        ), patch(
            "src.services.telegram.bot.handlers.LLMInitializer.initialize",
            new=AsyncMock(),
        ), patch(
            "src.services.telegram.bot.handlers.get_checkpointer",
            new=AsyncMock(),
        ), patch(
            "src.services.telegram.bot.handlers.close_calendar_client",
            new=AsyncMock(),
        ), patch(
            "src.services.telegram.bot.handlers.close_reminders_client",
            new=AsyncMock(),
        ), patch(
            "src.services.telegram.bot.handlers.close_checkpointer",
            new=AsyncMock(),
        ):
            await on_startup()
            await on_shutdown()

        database.setup.assert_awaited_once()
        database.create_tables.assert_awaited_once()
        database.close.assert_awaited_once()

    async def test_provider_upstream_diagnostic_has_a_cooldown_slot(self):
        redis = FakeRedis()
        config = type("Config", (), {"redis_client": redis})()

        with patch("src.services.web.app.get_config", return_value=config):
            self.assertTrue(await _acquire_provider_diagnostic_slot(42, 7))
            self.assertFalse(await _acquire_provider_diagnostic_slot(42, 7))
            self.assertTrue(await _acquire_provider_diagnostic_slot(42, 8))

    def test_login_code_is_numeric_and_exactly_eight_digits(self):
        code = generate_login_code()

        self.assertRegex(code, r"^\d{8}$")
        self.assertEqual(normalize_login_code(f"  {code} "), code)

    def test_telegram_model_wizard_has_progress_and_navigation(self):
        keyboard = _setup_keyboard()
        self.assertEqual(keyboard.inline_keyboard[0][0].text, "⬅️ Назад к моделям")
        self.assertEqual(keyboard.inline_keyboard[0][1].text, "❌ Отмена")
        self.assertIn("Шаг 1/2", _setup_prompt("openai", "model"))
        self.assertIn("Шаг 2/2", _setup_prompt("openai", "api_key"))

    def test_web_model_selector_distinguishes_profiles_and_fallbacks(self):
        from pathlib import Path

        source = Path("src/services/web/static/app.js").read_text(encoding="utf-8")
        app_source = Path("src/services/web/app.py").read_text(encoding="utf-8")
        self.assertIn("profiles.map", source)
        self.assertIn("models.map", source)
        self.assertIn('value.startsWith("profile:")', source)
        self.assertIn("/model-profiles/", source)
        self.assertIn('await get_model_profiles().deactivate(user_id)', app_source)
        self.assertIn("no_active_profile", source)

    def test_operator_fallback_is_explicitly_opt_in(self):
        from os import environ
        from unittest.mock import patch

        from src.agents.llms.initializer import LLMInitializer

        with patch.dict(environ, {"ALLOW_OPERATOR_FALLBACK": "false"}, clear=False):
            with self.assertRaises(RuntimeError):
                LLMInitializer.get_selected()

    def test_telegram_wizard_source_deletes_failed_api_key_messages(self):
        from pathlib import Path

        source = Path("src/services/telegram/bot/handlers.py").read_text(
            encoding="utf-8"
        )
        failure_branch = source.split(
            'except (ProviderConfigurationError, ValueError, RuntimeError):',
            2,
        )[2]
        self.assertIn("await message.delete()", failure_branch)

    def test_telegram_navigation_uses_commands_and_inline_screens(self):
        from pathlib import Path

        source = Path("src/services/telegram/bot/handlers.py").read_text(
            encoding="utf-8"
        )
        for label in (
            "💬 Открыть чат",
            "🤖 Мои модели",
            "🌐 Войти в Web UI",
            "ℹ️ Помощь",
        ):
            self.assertIn(label, source)
        self.assertIn('@dp.message(Command("start"))', source)
        self.assertIn('@dp.message(Command("menu"))', source)
        self.assertIn('@dp.message(Command("chat"))', source)
        self.assertIn('@dp.message(Command("cancel"))', source)
        self.assertIn("EXIT_CHAT_TEXT", source)
        self.assertIn("ReplyKeyboardMarkup", source)
        self.assertIn("ReplyKeyboardRemove", source)
        self.assertIn("callback_owner_guard", source)
        self.assertIn('message.chat.type != "private"', source)
        self.assertIn("class TelegramMode", Path(
            "src/services/telegram/bot/states.py"
        ).read_text(encoding="utf-8"))
        self.assertNotIn("nav:calendar:", source)
        self.assertNotIn("nav:reminders:", source)

    def test_telegram_commands_are_registered_for_chat_navigation(self):
        from pathlib import Path

        source = Path("src/services/telegram/bot/main.py").read_text(
            encoding="utf-8"
        )
        for command in (
            'command="start"',
            'command="menu"',
            'command="chat"',
            'command="cancel"',
            'command="calendar"',
            'command="reminders"',
            'command="models"',
            'command="web"',
            'command="help"',
        ):
            self.assertIn(command, source)

    def test_telegram_model_callbacks_reject_malformed_profile_ids(self):
        self.assertEqual(_profile_id_from_callback("model:activate:42"), 42)
        self.assertEqual(_profile_id_from_callback("model:delete:1"), 1)
        self.assertIsNone(_profile_id_from_callback("model:activate:not-an-id"))
        self.assertIsNone(_profile_id_from_callback("model:delete:0"))
        self.assertIsNone(_profile_id_from_callback("model:activate:"))

    def test_telegram_callback_flows_preserve_callback_user_identity(self):
        from pathlib import Path

        source = Path("src/services/telegram/bot/handlers.py").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            "await _send_models(callback.message, callback.from_user.id)",
            source,
        )
        self.assertIn(
            "await handle_web_login(callback.message, state, callback.from_user.id)",
            source,
        )
        self.assertIn("def _profile_id_from_callback", source)

    def test_agent_prompt_preserves_event_and_reminder_semantics(self):
        from pathlib import Path

        source = Path("src/agents/prompts/system.py").read_text(encoding="utf-8")
        self.assertIn("meaning is unchanged", source)
        self.assertIn("Never silently change dates", source)
        self.assertIn("Require explicit intent", source)
        self.assertIn("identify the exact existing event/reminder", source)

    def test_guided_model_setup_uses_safe_intents_and_confirmation(self):
        from pathlib import Path

        source = Path("src/services/telegram/bot/handlers.py").read_text(
            encoding="utf-8"
        )
        guidance = Path(
            "src/services/telegram/model_setup_guidance.py"
        ).read_text(encoding="utf-8")
        self.assertIn("detect_model_setup_request", source)
        self.assertIn("guided:model:start:", source)
        self.assertIn("ModelSetupIntent.LIST_PROVIDERS", source)
        self.assertIn("ModelSetupIntent.SHOW_SETUP_HELP", source)
        self.assertIn("Запуск настройки требует подтверждения", source)
        self.assertIn("format_provider_help", guidance)

    def test_guided_model_setup_parser_requires_exact_safe_phrases(self):
        from src.services.telegram.model_setup_guidance import (
            ModelSetupIntent,
            detect_model_setup_request,
        )

        request = detect_model_setup_request("добавить модель")
        self.assertIsNotNone(request)
        self.assertIs(request.intent, ModelSetupIntent.START_MODEL_SETUP)
        self.assertIsNone(detect_model_setup_request("не добавляй модель"))
        self.assertIsNone(
            detect_model_setup_request("обсудим, как добавить модель позже")
        )

    def test_mcp_success_result_keeps_machine_data(self):
        result = tool_success("created", {"event_id": "event-1"})

        self.assertTrue(result["ok"])
        self.assertEqual(result["code"], "ok")
        self.assertEqual(result["data"]["event_id"], "event-1")

    def test_mcp_failure_result_is_not_success_shaped(self):
        result = tool_failure("not_authorized", "Calendar authorization required")

        self.assertFalse(result["ok"])
        self.assertNotEqual(result["code"], "ok")
        self.assertIsNone(result["data"])

    def test_calendar_list_helper_handles_invalid_payload(self):
        result = event_list_result(
            200,
            ["not", "an", "object"],
            empty_message="No events",
            heading="Events",
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["code"], "invalid_response")

    def test_calendar_event_helper_returns_event_data(self):
        event = {"id": "event-1", "summary": "Meeting"}

        result = event_result(200, {"event": event}, "event-1")

        self.assertTrue(result["ok"])
        self.assertEqual(result["data"]["event"], event)

    def test_memory_path_isolated_and_rejects_traversal(self):
        self.assertEqual(user_memory_path(42), "/memory/users/42/AGENTS.md")
        with self.assertRaises(ValueError):
            normalize_memory_user_id("../../42")

    def test_observability_removes_sensitive_fields(self):
        with patch("utils.observability.logger.info") as log_info:
            emit_event(
                "auth.attempt",
                code="12345678",
                password="secret",
                user_id=42,
            )

        payload = json.loads(log_info.call_args.args[1])
        self.assertEqual(payload["user_id"], 42)
        self.assertNotIn("code", payload)
        self.assertNotIn("password", payload)

    def test_observability_redacts_nested_provider_credentials(self):
        with patch("utils.observability.logger.info") as log_info:
            emit_event(
                "provider.validation.failed",
                provider="openai",
                diagnostics={
                    "api_key": "sk-live-secret",
                    "status": "invalid",
                },
            )

        payload = json.loads(log_info.call_args.args[1])
        self.assertEqual(payload["diagnostics"]["api_key"], "[REDACTED]")
        self.assertEqual(payload["diagnostics"]["status"], "invalid")

    def test_provider_errors_have_safe_user_messages(self):
        self.assertIn("вовремя", provider_user_message(ProviderTimeoutError()))
        self.assertIn("отклонил", provider_user_message(ProviderRequestError()))

    async def test_openai_adapter_normalizes_constructor_timeout(self):
        config = type(
            "Config",
            (),
            {
                "BASE_LLM_CONFIG": type(
                    "Base",
                    (),
                    {
                        "MAX_TOKENS": 10,
                        "TEMPERATURE": 0,
                        "TIMEOUT": 1,
                        "VERBOSE": False,
                        "TOP_P": 1,
                    },
                )()
            },
        )()
        with patch("src.agents.providers.adapters.get_config", return_value=config):
            with patch(
                "src.agents.providers.adapters.ChatOpenAI",
                side_effect=TimeoutError(),
            ):
                with self.assertRaises(ProviderTimeoutError):
                    await OpenAIProvider().create_model(
                        ProviderContext(1, "gpt-4o-mini", "key")
                    )

    def test_user_model_factory_cache_is_bounded_and_invalidatable(self):
        UserModelFactory._cache.clear()
        UserModelFactory._cache_limit = 1
        sentinel = object()
        UserModelFactory._cache[(1, 1, "one")] = sentinel
        UserModelFactory._cache[(2, 2, "two")] = sentinel
        while len(UserModelFactory._cache) > UserModelFactory._cache_limit:
            UserModelFactory._cache.popitem(last=False)
        self.assertEqual(len(UserModelFactory._cache), 1)
        UserModelFactory.invalidate_user(2)
        self.assertNotIn((2, 2, "two"), UserModelFactory._cache)
        UserModelFactory._cache.clear()
        UserModelFactory._cache_limit = 64

    async def test_user_model_factory_reuses_and_refreshes_profile_runtime(self):
        class Adapter(ProviderAdapter):
            capabilities = type(
                "Capabilities",
                (),
                {
                    "provider": ModelProvider.OLLAMA,
                    "display_name": "Ollama",
                    "requires_user_api_key": False,
                    "developer_managed": True,
                },
            )()

            def __init__(self):
                self.created = 0

            async def validate(self, context):
                return None

            async def create_model(self, context):
                self.created += 1
                return object()

        class Registry:
            def __init__(self, adapter):
                self.adapter = adapter

            def get(self, provider):
                return self.adapter

        class Profiles:
            def __init__(self):
                self.api_key = "first"
                self.profile = UserModelProfile(
                    1, 42, ModelProvider.OLLAMA, "llama", "Llama", True
                )

            async def list_for_user(self, user_id):
                return [self.profile]

            async def get_api_key(self, user_id, profile_id):
                return self.api_key

        UserModelFactory._cache.clear()
        profiles = Profiles()
        adapter = Adapter()
        factory = UserModelFactory(profiles, Registry(adapter))
        first = await factory.create_for_profile(42, 1)
        second = await factory.create_for_profile(42, 1)
        profiles.api_key = "rotated"
        third = await factory.create_for_profile(42, 1)

        self.assertIs(first, second)
        self.assertIsNot(second, third)
        self.assertEqual(adapter.created, 2)
        UserModelFactory._cache.clear()

    def test_timed_event_emits_completion_duration(self):
        with patch("utils.observability.emit_event") as emit:
            with timed_event("test.operation", user_id=42):
                pass

        emit.assert_called_once()
        self.assertEqual(emit.call_args.args[0], "test.operation.completed")
        self.assertIn("duration_ms", emit.call_args.kwargs)

    def test_token_usage_handles_none_metadata(self):
        chunk = type(
            "Chunk",
            (),
            {"usage_metadata": None, "response_metadata": None},
        )()

        self.assertEqual(
            extract_token_usage(chunk),
            {
                "model": None,
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
            },
        )

    def test_token_usage_supports_provider_prompt_completion_names(self):
        chunk = type(
            "Chunk",
            (),
            {
                "usage_metadata": None,
                "response_metadata": {
                    "model_name": "provider-model",
                    "usage": {
                        "prompt_tokens": 11,
                        "completion_tokens": 7,
                    },
                },
            },
        )()

        usage = extract_token_usage(chunk)

        self.assertEqual(usage["model"], "provider-model")
        self.assertEqual(usage["input_tokens"], 11)
        self.assertEqual(usage["output_tokens"], 7)
        self.assertEqual(usage["total_tokens"], 18)

    async def test_model_profile_service_requires_keys_only_for_user_managed_providers(self):
        class Profiles:
            async def list_for_user(self, user_id):
                return []

            async def create(self, user_id, provider, model_name, display_name, api_key):
                return UserModelProfile(1, user_id, provider, model_name, display_name, False)

            async def list_for_user(self, user_id):
                return []

            async def get_active(self, user_id):
                return None

            async def activate(self, user_id, profile_id):
                raise AssertionError

            async def delete(self, user_id, profile_id):
                raise AssertionError

            async def get_api_key(self, user_id, profile_id):
                return None

        service = ModelProfileService(
            Profiles(),
            limits=type(
                "Limits",
                (),
                {
                    "MAX_MODEL_PROFILES": 10,
                    "MAX_MODEL_NAME_LENGTH": 200,
                    "MAX_DISPLAY_NAME_LENGTH": 200,
                },
            )(),
        )
        with self.assertRaises(ValueError):
            await service.add(1, ModelProvider.OPENAI, "gpt-4o-mini", "OpenAI")
        with self.assertRaises(ValueError):
            await service.add(
                1,
                ModelProvider.OPENAI,
                "gpt-4o-mini",
                "OpenAI",
                api_key="   ",
            )

        profile = await service.add(
            1,
            ModelProvider.OLLAMA,
            "llama3.2",
            "Free Ollama",
            api_key="must-be-ignored",
        )
        self.assertEqual(profile.provider, ModelProvider.OLLAMA)

    async def test_model_profile_service_enforces_profile_name_limits(self):
        class Profiles:
            async def list_for_user(self, user_id):
                return []

            async def create(self, *args):
                raise AssertionError("profile must be rejected")

        class Limits:
            MAX_MODEL_PROFILES = 10
            MAX_MODEL_NAME_LENGTH = 4
            MAX_DISPLAY_NAME_LENGTH = 4

        service = ModelProfileService(Profiles(), limits=Limits())
        with self.assertRaisesRegex(ValueError, "too long"):
            await service.add(1, ModelProvider.OLLAMA, "llama3.2", "Ollama")
        with self.assertRaisesRegex(ValueError, "too long"):
            await service.add(1, ModelProvider.OLLAMA, "ok", "Ollama")

        class FullProfiles(Profiles):
            async def list_for_user(self, user_id):
                return [object()] * 10

        with self.assertRaisesRegex(ValueError, "limit"):
            await ModelProfileService(
                FullProfiles(),
                limits=type(
                    "ProfileLimit",
                    (),
                    {
                        "MAX_MODEL_PROFILES": 10,
                        "MAX_MODEL_NAME_LENGTH": 200,
                        "MAX_DISPLAY_NAME_LENGTH": 200,
                    },
                )(),
            ).add(1, ModelProvider.OLLAMA, "ok", "ok")

    async def test_model_profile_diagnostics_are_safe_and_can_check_upstream(self):
        class Profiles:
            async def list_for_user(self, user_id):
                return [
                    UserModelProfile(
                        7, user_id, ModelProvider.OLLAMA, "llama3.2", "Ollama", True
                    )
                ]

            async def get_api_key(self, user_id, profile_id):
                return None

        class Adapter(ProviderAdapter):
            capabilities = ProviderCapabilities(
                ModelProvider.OLLAMA, "Ollama", False, developer_managed=True
            )

            def __init__(self):
                self.checked = []

            async def validate(self, context):
                self.checked.append("validate")

            async def create_model(self, context):
                class Model:
                    async def ainvoke(inner_self, prompt):
                        self.checked.append(prompt)
                        return "OK"

                return Model()

        adapter = Adapter()
        registry = type(
            "Registry",
            (),
            {
                "get": lambda self, provider: adapter,
            },
        )()
        service = ModelProfileService(
            Profiles(),
            registry=registry,
            limits=type(
                "Limits",
                (),
                {
                    "MAX_MODEL_PROFILES": 10,
                    "MAX_MODEL_NAME_LENGTH": 200,
                    "MAX_DISPLAY_NAME_LENGTH": 200,
                },
            )(),
        )

        with patch("src.services.model_profiles.emit_event") as emit:
            local = await service.diagnose(42, 7)
            self.assertEqual(emit.call_args.kwargs["diagnostic_mode"], "local")
            upstream = await service.diagnose(42, 7, check_upstream=True)
            self.assertEqual(emit.call_args.kwargs["diagnostic_mode"], "upstream")

        self.assertEqual(local.status, "healthy")
        self.assertFalse(local.upstream_checked)
        self.assertEqual(upstream.message, "Провайдер отвечает")
        self.assertTrue(upstream.upstream_checked)
        self.assertEqual(adapter.checked, ["validate", "validate", "Reply with OK."])

    async def test_model_profile_diagnostics_map_upstream_failure_safely(self):
        class Profiles:
            async def list_for_user(self, user_id):
                return [
                    UserModelProfile(
                        8, user_id, ModelProvider.OLLAMA, "llama3.2", "Ollama", True
                    )
                ]

            async def get_api_key(self, user_id, profile_id):
                return None

        class Adapter(ProviderAdapter):
            capabilities = ProviderCapabilities(
                ModelProvider.OLLAMA, "Ollama", False, developer_managed=True
            )

            async def validate(self, context):
                return None

            async def create_model(self, context):
                class Model:
                    async def ainvoke(self, prompt):
                        raise ProviderTimeoutError("internal timeout")

                return Model()

        registry = type(
            "Registry",
            (),
            {"get": lambda self, provider: Adapter()},
        )()
        service = ModelProfileService(
            Profiles(),
            registry=registry,
            limits=type(
                "Limits",
                (),
                {
                    "MAX_MODEL_PROFILES": 10,
                    "MAX_MODEL_NAME_LENGTH": 200,
                    "MAX_DISPLAY_NAME_LENGTH": 200,
                },
            )(),
        )

        result = await service.diagnose(42, 8, check_upstream=True)

        self.assertEqual(result.status, "unhealthy")
        self.assertIn("вовремя", result.message)
        self.assertNotIn("internal timeout", result.message)

    async def test_model_profile_audit_events_are_tenant_scoped_and_secret_free(self):
        class Profiles:
            async def list_for_user(self, user_id):
                return []

            async def create(
                self, user_id, provider, model_name, display_name, api_key
            ):
                return UserModelProfile(
                    9, user_id, provider, model_name, display_name, False
                )

        service = ModelProfileService(
            Profiles(),
            limits=type(
                "Limits",
                (),
                {
                    "MAX_MODEL_PROFILES": 10,
                    "MAX_MODEL_NAME_LENGTH": 200,
                    "MAX_DISPLAY_NAME_LENGTH": 200,
                },
            )(),
        )
        with patch("src.services.model_profiles.emit_event") as emit:
            await service.add(
                42,
                ModelProvider.OPENAI,
                "gpt-4o-mini",
                "OpenAI",
                api_key="sk-live-secret",
            )

        emit.assert_called_once()
        name, fields = emit.call_args.args[0], emit.call_args.kwargs
        self.assertEqual(name, "model_profile.audit")
        self.assertEqual(fields["user_id"], 42)
        self.assertEqual(fields["action"], "create")
        self.assertEqual(fields["result"], "succeeded")
        self.assertNotIn("api_key", fields)
        self.assertNotIn("sk-live-secret", str(fields))

    async def test_model_profile_diagnostics_audit_mode_and_internal_failure(self):
        class Profiles:
            async def list_for_user(self, user_id):
                return [
                    UserModelProfile(
                        10, user_id, ModelProvider.OLLAMA, "llama3.2", "Ollama", True
                    )
                ]

            async def get_api_key(self, user_id, profile_id):
                raise RuntimeError("repository unavailable")

        service = ModelProfileService(
            Profiles(),
            limits=type(
                "Limits",
                (),
                {
                    "MAX_MODEL_PROFILES": 10,
                    "MAX_MODEL_NAME_LENGTH": 200,
                    "MAX_DISPLAY_NAME_LENGTH": 200,
                },
            )(),
        )
        with patch("src.services.model_profiles.emit_event") as emit:
            with self.assertRaisesRegex(RuntimeError, "repository unavailable"):
                await service.diagnose(42, 10)

        fields = emit.call_args.kwargs
        self.assertEqual(fields["diagnostic_mode"], "local")
        self.assertEqual(fields["error_category"], "internal")

    async def test_model_profile_application_initializes_telegram_tenant(self):
        class Users:
            def __init__(self):
                self.ids = set()

            async def get_user_by_tg_id(self, tg_id):
                return object() if tg_id in self.ids else None

            async def add_user(self, tg_id, **kwargs):
                self.ids.add(tg_id)
                return object()

        class Profiles:
            async def list_for_user(self, user_id):
                return []

            async def create(self, user_id, provider, model_name, display_name, api_key):
                return UserModelProfile(
                    1, user_id, provider, model_name, display_name, False
                )

        class Transaction:
            async def __aenter__(self):
                return object()

            async def __aexit__(self, *args):
                return False

        class Database:
            def __init__(self):
                self.users = Users()
                self.profiles = Profiles()

            def transaction(self):
                return Transaction()

            def get_users_repo(self, session):
                return self.users

            def get_model_profiles_repo(self, session):
                return self.profiles

        config = type(
            "Config",
            (),
            {
                "TENANT_LIMITS": type(
                    "Limits",
                    (),
                    {
                        "MAX_MODEL_PROFILES": 10,
                        "MAX_MODEL_NAME_LENGTH": 200,
                        "MAX_DISPLAY_NAME_LENGTH": 200,
                    },
                )()
            },
        )()
        with patch("src.services.model_profiles.get_config", return_value=config):
            application = ModelProfileApplication(Database())
            profile = await application.add(
                777,
                ModelProvider.OLLAMA,
                "llama3.2",
                "Developer Ollama",
            )

        self.assertEqual(profile.user_id, 777)

    async def test_model_profile_application_owns_active_model_factory(self):
        class Profiles:
            async def get_active(self, user_id):
                return None

        class Transaction:
            async def __aenter__(self):
                return object()

            async def __aexit__(self, *args):
                return False

        class Database:
            def transaction(self):
                return Transaction()

            def get_model_profiles_repo(self, session):
                return Profiles()

        config = type(
            "Config",
            (),
            {
                "TENANT_LIMITS": type(
                    "Limits",
                    (),
                    {
                        "MAX_MODEL_PROFILES": 10,
                        "MAX_MODEL_NAME_LENGTH": 200,
                        "MAX_DISPLAY_NAME_LENGTH": 200,
                    },
                )()
            },
        )()
        with patch("src.services.model_profiles.get_config", return_value=config):
            application = ModelProfileApplication(Database())
            self.assertIsNone(await application.create_active_model(42))

    def test_model_profile_application_exposes_injected_provider_capabilities(self):
        class Registry:
            def capabilities(self):
                return (
                    ProviderCapabilities(
                        ModelProvider.OLLAMA,
                        "Test Ollama",
                        False,
                        developer_managed=True,
                    ),
                )

        application = ModelProfileApplication(object(), registry=Registry())
        self.assertEqual(application.available_providers()[0].display_name, "Test Ollama")

    async def test_model_profiles_repository_isolates_users_and_encrypts_keys(self):
        from cryptography.fernet import Fernet
        from db.sqlalchemy.models import Base, Users
        from db.sqlalchemy.model_profiles_crud import ModelProfilesORM

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            engine = create_async_engine(
                f"sqlite+aiosqlite:///{os.path.join(directory, 'profiles.db')}"
            )
            async with engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)
            sessions = async_sessionmaker(engine, expire_on_commit=False)
            with patch.dict("os.environ", {
                "TOKEN_ENCRYPTION_KEY": Fernet.generate_key().decode(),
            }):
                async with sessions() as session:
                    await session.execute(insert(Users), [{"tg_id": 101}, {"tg_id": 202}])
                    await session.commit()
                    repo = ModelProfilesORM(session)
                    profile = await repo.create(
                        101,
                        ModelProvider.OPENAI,
                        "gpt-4o-mini",
                        "Private OpenAI",
                        "secret-key",
                    )
                    await session.commit()
                    self.assertEqual(len(await repo.list_for_user(101)), 1)
                    self.assertEqual(len(await repo.list_for_user(202)), 0)
                    self.assertEqual(await repo.get_api_key(101, profile.id), "secret-key")
                    self.assertIsNone(await repo.get_api_key(202, profile.id))
            await engine.dispose()

    def test_token_cipher_rejects_invalid_key_with_actionable_message(self):
        from utils.crypto import TokenCipher

        with patch.dict("os.environ", {"TOKEN_ENCRYPTION_KEY": "token_key"}):
            with self.assertRaisesRegex(RuntimeError, "valid Fernet key"):
                TokenCipher()

    async def test_monitoring_ingest_and_stats(self):
        from src.services.monitoring import app as monitoring

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            with patch.dict("os.environ", {
                "MONITORING_API_KEY": "test-monitoring-key",
                "MONITORING_DB_PATH": os.path.join(directory, "monitoring.db"),
            }):
                await monitoring.ingest(monitoring.MonitoringEvent(
                    event="agent.invoke.completed",
                    model="test-model",
                    total_tokens=12,
                ), x_monitoring_key="test-monitoring-key")
                result = await monitoring.stats(
                    x_monitoring_key="test-monitoring-key"
                )

        self.assertEqual(result["events"]["agent.invoke.completed"], 1)
        self.assertEqual(result["tokens_by_model"]["test-model"], 12)

    async def test_monitoring_persistence_round_trip(self):
        from src.services.monitoring import app as monitoring

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            with patch.dict("os.environ", {
                "MONITORING_API_KEY": "test-monitoring-key",
                "MONITORING_DB_PATH": os.path.join(directory, "monitoring.db"),
            }):
                await monitoring.ingest(monitoring.MonitoringEvent(
                    event="persistent.event",
                    model="persistent-model",
                    total_tokens=9,
                ), x_monitoring_key="test-monitoring-key")
                result = await monitoring.stats(
                    x_monitoring_key="test-monitoring-key"
                )

        self.assertEqual(result["events"]["persistent.event"], 1)
        self.assertEqual(result["tokens_by_model"]["persistent-model"], 9)

    async def test_monitoring_schema_migration_is_idempotent(self):
        from db.sqlalchemy.monitoring_crud import MonitoringORM

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            repository = MonitoringORM(
                f"sqlite+aiosqlite:///{os.path.join(directory, 'schema.db')}"
            )
            self.assertFalse(await repository.create_tables())
            self.assertTrue(await repository.create_tables())
            await repository.close()

    async def test_schema_migration_reports_upgrade_and_rejects_newer_version(self):
        from sqlalchemy import text
        from db.sqlalchemy.migrations import check_database, migrate_database
        from db.sqlalchemy.models import Base

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            engine = create_async_engine(
                f"sqlite+aiosqlite:///{os.path.join(directory, 'schema.db')}"
            )
            status = await check_database(engine)
            self.assertEqual(status.current_version, 0)
            self.assertTrue(status.upgrade_required)
            self.assertFalse(
                await migrate_database(
                    engine,
                    Base.metadata,
                    extra_tables=("users", "google_tokens", "model_profiles"),
                )
            )
            current = await check_database(
                engine,
                required_tables=("users", "google_tokens", "model_profiles"),
            )
            self.assertEqual(current.current_version, 4)
            self.assertFalse(current.upgrade_required)
            async with engine.begin() as connection:
                await connection.execute(
                    text("INSERT INTO schema_migrations (version) VALUES (99)")
                )
            with self.assertRaisesRegex(RuntimeError, "newer than supported"):
                await check_database(engine)
            async with engine.begin() as connection:
                await connection.execute(text("DELETE FROM schema_migrations WHERE version = 99"))
                await connection.execute(text("DROP TABLE model_profiles"))
            with self.assertRaisesRegex(RuntimeError, "missing required tables"):
                await check_database(
                    engine,
                    required_tables=("users", "google_tokens", "model_profiles"),
                )
            await engine.dispose()

    async def test_schema_migration_repairs_partial_v1_baseline(self):
        from sqlalchemy import text
        from db.sqlalchemy.migrations import check_database, migrate_database
        from db.sqlalchemy.models import Base

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            engine = create_async_engine(
                f"sqlite+aiosqlite:///{os.path.join(directory, 'partial.db')}"
            )
            async with engine.begin() as connection:
                await connection.execute(
                    text(
                        "CREATE TABLE schema_migrations "
                        "(version INTEGER PRIMARY KEY, applied_at TIMESTAMP)"
                    )
                )
                await connection.execute(
                    text("INSERT INTO schema_migrations (version) VALUES (1)")
                )

            self.assertFalse(
                await migrate_database(
                    engine,
                    Base.metadata,
                    extra_tables=("users", "google_tokens", "model_profiles"),
                )
            )
            status = await check_database(
                engine,
                required_tables=("users", "google_tokens", "model_profiles"),
            )
            self.assertEqual(status.current_version, 4)
            self.assertFalse(status.upgrade_required)
            await engine.dispose()

    async def test_monitoring_rejects_invalid_api_key(self):
        from src.services.monitoring import app as monitoring

        with patch.dict("os.environ", {"MONITORING_API_KEY": "expected"}):
            with self.assertRaises(Exception):
                await monitoring.ingest(
                    monitoring.MonitoringEvent(event="test"),
                    x_monitoring_key="wrong",
                )

    async def test_monitoring_rejects_missing_api_key_configuration(self):
        from src.services.monitoring import app as monitoring

        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaisesRegex(
                HTTPException,
                "authentication is not configured",
            ):
                await monitoring.ingest(
                    monitoring.MonitoringEvent(event="test"),
                )

    def test_monitoring_accepts_integer_user_id_from_observability(self):
        from src.services.monitoring.app import MonitoringEvent

        event = MonitoringEvent(
            event="web.authenticated",
            user_id=1694304302,
        )

        self.assertEqual(event.user_id, 1694304302)

    async def test_websocket_rejects_untrusted_origin_before_accept(self):
        from src.services.web.app import websocket_chat

        class FakeWebSocket:
            cookies = {}
            headers = {"origin": "https://evil.example"}

            async def close(self, code, reason):
                self.closed = (code, reason)

        websocket = FakeWebSocket()
        with patch.dict(
            "os.environ",
            {"CORS_ORIGINS": "https://assistant.example"},
            clear=True,
        ):
            await websocket_chat(websocket)

        self.assertEqual(websocket.closed, (1008, "Origin not allowed"))

    async def test_monitoring_dashboard_is_available(self):
        from src.services.monitoring.app import dashboard

        page = await dashboard()

        self.assertIn("PortableAgent Monitoring", page.body.decode())
        self.assertIn("/stats", page.body.decode())

    async def test_calendar_service_requires_internal_api_key(self):
        from src.services.base import create_app
        from fastapi import APIRouter

        router = APIRouter()

        @router.get("/protected")
        async def protected():
            return {"ok": True}

        test_app = create_app("Calendar", [router], internal_auth=True)
        with patch.dict("os.environ", {"INTERNAL_API_KEY": "expected"}):
            from starlette.testclient import TestClient
            client = TestClient(test_app)
            response = client.get("/health")
            self.assertEqual(response.status_code, 200)
            response = client.get("/protected")
            self.assertEqual(response.status_code, 401)
            response = client.get(
                "/protected",
                headers={"X-Internal-Api-Key": "expected"},
            )
            self.assertEqual(response.status_code, 200)

    async def test_websocket_selection_is_tenant_scoped_and_active(self):
        from types import SimpleNamespace

        class Context:
            async def __aenter__(self):
                return repository

            async def __aexit__(self, *_):
                return False

        redis = SimpleNamespace(get=AsyncMock(return_value="conversation-1"))
        config = SimpleNamespace(redis_client=redis)
        repository = SimpleNamespace(
            get=AsyncMock(return_value=SimpleNamespace(
                id="conversation-1", thread_id="conversation-thread-1", archived_at=None
            ))
        )
        with patch("src.services.web.app.get_config", return_value=config), patch(
            "src.services.web.app.conversation_repository",
            return_value=Context(),
        ):
            selected = await _selected_web_conversation(7, "thread-7")
        self.assertEqual(selected.id, "conversation-1")
        self.assertEqual(selected.thread_id, "conversation-thread-1")
        repository.get.assert_awaited_once_with(7, "conversation-1")

    async def test_websocket_selection_rejects_missing_or_archived(self):
        from types import SimpleNamespace

        redis = SimpleNamespace(get=AsyncMock(return_value=None))
        config = SimpleNamespace(redis_client=redis)
        with patch("src.services.web.app.get_config", return_value=config), patch(
            "src.services.web.app.conversation_repository"
        ) as repository:
            self.assertIsNone(await _selected_web_conversation(7, "thread-7"))
            repository.assert_not_called()


if __name__ == "__main__":
    unittest.main()
