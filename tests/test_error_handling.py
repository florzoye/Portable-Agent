import os
import unittest
from unittest.mock import patch
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import aiohttp
from cryptography.fernet import Fernet

from src.services.reminders.mcp.server import (
    create_followup,
    create_reminder,
    get_current_time,
)
from utils.client_session import AsyncHTTPClient
from utils.crypto import TokenCipher
from utils.helpers import DateTimeNormalizer
from src.models.events import EventsRangeRequest, SearchEventsRequest
from src.agents.prompts.system import AgentSystemPrompt
from src.agents.middleware import UserContextMiddleware
from src.agents.memory import normalize_memory_user_id, user_memory_path
from data.configs.tg_config import TelegramSettings
from src.services.web.one_time_code import (
    generate_login_code,
    login_attempt_key,
    login_code_key,
    normalize_login_code,
)
from src.services.web.app import _get_session_context


class FakeResponse:
    status = 502
    headers = {"content-type": "application/json"}

    async def json(self):
        raise aiohttp.ContentTypeError(
            request_info=None,
            history=(),
            message="invalid JSON",
        )

    async def text(self):
        return "upstream returned invalid JSON"


class FakeRedisSession:
    def __init__(self):
        self.values = {
            "web_session:token": "42",
            "web_session_thread:token": "thread-1",
        }
        self.expired = []

    async def get(self, key):
        return self.values.get(key)

    async def expire(self, key, ttl):
        self.expired.append((key, ttl))


class ErrorHandlingTests(unittest.IsolatedAsyncioTestCase):
    async def test_http_client_returns_text_for_invalid_json(self):
        client = AsyncHTTPClient()

        status, body = await client._handle_response(FakeResponse())

        self.assertEqual(status, 502)
        self.assertEqual(body, "upstream returned invalid JSON")

    async def test_http_client_requires_initialized_session(self):
        with self.assertRaises(RuntimeError):
            AsyncHTTPClient()._get_session()

    async def test_invalid_timezone_falls_back_to_utc(self):
        result = get_current_time("Not/A_Timezone")

        self.assertIn("Current time in UTC:", result["message"])
        self.assertIn("UTC offset: +0000", result["message"])

    async def test_invalid_reminder_datetime_returns_safe_error(self):
        result = await create_reminder(
            user_id="1",
            text="test",
            remind_at="not-a-datetime",
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["code"], "invalid_reminder")

    async def test_past_followup_is_not_scheduled(self):
        with patch(
            "src.tasks.tasks.followup_after_event.apply_async"
        ) as apply_async:
            result = await create_followup(
                tg_id=1,
                event_title="past event",
                followup_at="2000-01-01T00:00:00+00:00",
            )

        self.assertFalse(result["ok"])
        self.assertEqual(result["code"], "past_time")
        apply_async.assert_not_called()

    async def test_token_cipher_round_trip_and_invalid_token(self):
        key = Fernet.generate_key().decode()
        with patch.dict(os.environ, {"TOKEN_ENCRYPTION_KEY": key}):
            cipher = TokenCipher()
            encrypted = cipher.encrypt("secret")

            self.assertNotEqual(encrypted, "secret")
            self.assertEqual(cipher.decrypt(encrypted), "secret")
            with self.assertRaises(ValueError):
                cipher.decrypt("invalid-token")

    def test_expiry_is_converted_to_utc_before_timezone_is_removed(self):
        expiry = datetime(2026, 1, 1, 12, tzinfo=ZoneInfo("Europe/Moscow"))

        normalized = DateTimeNormalizer.normalize_expiry_for_db(expiry)

        self.assertEqual(normalized, datetime(2026, 1, 1, 9))

    def test_event_range_requires_timezone(self):
        with self.assertRaises(ValueError):
            EventsRangeRequest(
                user_id=1,
                start="2026-01-01T10:00:00",
                end="2026-01-01T11:00:00",
            )

    def test_search_window_is_bounded(self):
        with self.assertRaises(ValueError):
            SearchEventsRequest(
                user_id=1,
                query="meeting",
                days_ahead=91,
            )

    def test_system_prompt_contains_tool_verification_rules(self):
        prompt = AgentSystemPrompt.get_prompt(
            memory_path="/memory/users/1/AGENTS.md",
            tg_id=1,
            channel="web",
        ).content

        self.assertIn("After every write operation, verify the result", prompt)
        self.assertIn("Treat a tool call as successful only when `ok` is exactly `true`", prompt)
        self.assertIn("Use `data` for factual IDs, events, timestamps", prompt)
        self.assertIn("Never store tool payloads, transient errors", prompt)
        self.assertIn("for create_followup pass it as tg_id", prompt)
        self.assertIn('channel="web"', prompt)

    async def test_user_context_overrides_model_tool_arguments(self):
        middleware = UserContextMiddleware(user_id="42", channel="web")
        request = type(
            "Request",
            (),
            {
                "tool_call": {
                    "name": "create_reminder",
                    "args": {
                        "user_id": "999",
                        "channel": "telegram",
                        "text": "test",
                    },
                    "id": "call-1",
                },
                "override": lambda self, **kwargs: type(
                    "Request",
                    (),
                    {
                        "tool_call": kwargs["tool_call"],
                        "override": self.override,
                    },
                )(),
            },
        )()

        async def handler(bound_request):
            return bound_request.tool_call["args"]

        result = await middleware.awrap_tool_call(request, handler)

        self.assertEqual(result["user_id"], "42")
        self.assertEqual(result["channel"], "web")

    def test_telegram_proxy_accepts_supported_schemes(self):
        settings = TelegramSettings(
            BOT_TOKEN="test-token",
            TELEGRAM_PROXY="socks5://proxy.example:1080",
        )

        self.assertEqual(settings.TELEGRAM_PROXY, "socks5://proxy.example:1080")

    def test_telegram_proxy_rejects_unsupported_scheme(self):
        with self.assertRaises(ValueError):
            TelegramSettings(
                BOT_TOKEN="test-token",
                TELEGRAM_PROXY="ftp://proxy.example:21",
            )

    def test_web_login_code_is_numeric_and_fixed_length(self):
        code = generate_login_code()
        self.assertEqual(len(code), 8)
        self.assertEqual(normalize_login_code(code), code)

    def test_web_login_code_rejects_invalid_value(self):
        with self.assertRaises(ValueError):
            normalize_login_code("1234")

    def test_tool_result_has_stable_success_and_failure_shape(self):
        from src.services.tool_result import tool_failure, tool_success

        self.assertEqual(
            tool_success("created", {"id": "event-1"}),
            {
                "ok": True,
                "code": "ok",
                "message": "created",
                "data": {"id": "event-1"},
            },
        )
        self.assertEqual(
            tool_failure("not_found", "missing"),
            {
                "ok": False,
                "code": "not_found",
                "message": "missing",
                "data": None,
            },
        )

    def test_observability_event_does_not_include_sensitive_fields(self):
        from unittest.mock import patch
        from utils.observability import emit_event

        with patch("utils.observability.logger.info") as log_info:
            emit_event("auth", code="12345678", user_id=42)

        payload = log_info.call_args.args[1]
        self.assertNotIn("12345678", payload)
        self.assertIn('"user_id": 42', payload)

    def test_calendar_event_list_helper_normalizes_responses(self):
        from src.services.calendar.mcp.common import event_list_result

        result = event_list_result(
            200,
            {"events": []},
            empty_message="No events",
            heading="Events",
        )

        self.assertEqual(result["code"], "ok")
        self.assertEqual(result["data"], {"events": []})

    def test_reminder_datetime_helper_applies_timezone_and_utc_conversion(self):
        from src.services.reminders.mcp.common import parse_scheduled_datetime

        scheduled, _, timezone_name = parse_scheduled_datetime(
            "2026-01-01T12:00:00",
            "Europe/Moscow",
        )

        self.assertEqual(timezone_name, "Europe/Moscow")
        self.assertEqual(scheduled.astimezone(timezone.utc).hour, 9)

    def test_memory_path_is_stable_for_a_user(self):
        self.assertEqual(
            user_memory_path(42),
            "/memory/users/42/AGENTS.md",
        )
        self.assertEqual(
            user_memory_path("42"),
            "/memory/users/42/AGENTS.md",
        )

    def test_memory_user_id_rejects_path_traversal(self):
        with self.assertRaises(ValueError):
            normalize_memory_user_id("../other-user")
    def test_web_login_code_uses_scoped_redis_keys(self):
        self.assertEqual(login_code_key("12345678"), "web_login_code:12345678")
        self.assertEqual(
            login_attempt_key("127.0.0.1"),
            "web_login_attempts:127.0.0.1",
        )

    async def test_web_session_context_returns_server_thread_and_refreshes_ttl(self):
        redis = FakeRedisSession()
        config = type("Config", (), {"redis_client": redis})()

        with patch("src.services.web.app.get_config", return_value=config):
            context = await _get_session_context("token")

        self.assertEqual(context, (42, "thread-1"))
        self.assertEqual(
            redis.expired,
            [
                ("web_session:token", 86400),
                ("web_session_thread:token", 86400),
            ],
        )


if __name__ == "__main__":
    unittest.main()
