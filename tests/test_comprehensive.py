import json
import os
import tempfile
import unittest
from unittest.mock import patch
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy import insert

from fastapi import HTTPException

from src.agents.memory import normalize_memory_user_id, user_memory_path
from src.services.calendar.mcp.common import event_list_result, event_result
from src.services.tool_result import tool_failure, tool_success
from src.services.web.app import (
    _acquire_provider_diagnostic_slot,
    _get_session_context,
)
from src.services.telegram.bot.handlers import _setup_keyboard, _setup_prompt
from src.services.web.one_time_code import (
    generate_login_code,
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

    async def test_missing_session_is_rejected(self):
        redis = FakeRedis()
        config = type("Config", (), {"redis_client": redis})()

        with patch("src.services.web.app.get_config", return_value=config):
            with self.assertRaises(HTTPException) as error:
                await _get_session_context("missing")

        self.assertEqual(error.exception.status_code, 401)

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
                "MONITORING_API_KEY": "",
                "MONITORING_DB_PATH": os.path.join(directory, "monitoring.db"),
            }):
                await monitoring.ingest(monitoring.MonitoringEvent(
                    event="agent.invoke.completed",
                    model="test-model",
                    total_tokens=12,
                ))
                result = await monitoring.stats()

        self.assertEqual(result["events"]["agent.invoke.completed"], 1)
        self.assertEqual(result["tokens_by_model"]["test-model"], 12)

    async def test_monitoring_persistence_round_trip(self):
        from src.services.monitoring import app as monitoring

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as directory:
            with patch.dict("os.environ", {
                "MONITORING_API_KEY": "",
                "MONITORING_DB_PATH": os.path.join(directory, "monitoring.db"),
            }):
                await monitoring.ingest(monitoring.MonitoringEvent(
                    event="persistent.event",
                    model="persistent-model",
                    total_tokens=9,
                ))
                result = await monitoring.stats()

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
            self.assertEqual(current.current_version, 1)
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

    async def test_monitoring_rejects_invalid_api_key(self):
        from src.services.monitoring import app as monitoring

        with patch.dict("os.environ", {"MONITORING_API_KEY": "expected"}):
            with self.assertRaises(Exception):
                await monitoring.ingest(
                    monitoring.MonitoringEvent(event="test"),
                    x_monitoring_key="wrong",
                )

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


if __name__ == "__main__":
    unittest.main()
