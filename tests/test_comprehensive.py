import json
import unittest
from unittest.mock import patch

from fastapi import HTTPException

from src.agents.memory import normalize_memory_user_id, user_memory_path
from src.services.calendar.mcp.common import event_list_result, event_result
from src.services.tool_result import tool_failure, tool_success
from src.services.web.app import _get_session_context
from src.services.web.one_time_code import (
    generate_login_code,
    normalize_login_code,
)
from utils.observability import emit_event, timed_event
from utils.token_usage import extract_token_usage


class FakeRedis:
    def __init__(self, values=None):
        self.values = values or {}
        self.expired = []

    async def get(self, key):
        return self.values.get(key)

    async def expire(self, key, ttl):
        self.expired.append((key, ttl))


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

    def test_login_code_is_numeric_and_exactly_eight_digits(self):
        code = generate_login_code()

        self.assertRegex(code, r"^\d{8}$")
        self.assertEqual(normalize_login_code(f"  {code} "), code)

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

    async def test_monitoring_ingest_and_stats(self):
        from src.services.monitoring import app as monitoring

        monitoring.EVENTS.clear()
        monitoring.COUNTERS.clear()
        monitoring.TOKENS.clear()
        with patch.dict("os.environ", {"MONITORING_API_KEY": ""}):
            await monitoring.ingest(monitoring.MonitoringEvent(
                event="agent.invoke.completed",
                model="test-model",
                total_tokens=12,
            ))
            result = await monitoring.stats()

        self.assertEqual(result["events"]["agent.invoke.completed"], 1)
        self.assertEqual(result["tokens_by_model"]["test-model"], 12)

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
