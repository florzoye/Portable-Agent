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

        self.assertIn("Current time in UTC:", result)
        self.assertIn("UTC offset: +0000", result)

    async def test_invalid_reminder_datetime_returns_safe_error(self):
        result = await create_reminder(
            user_id="1",
            text="test",
            remind_at="not-a-datetime",
        )

        self.assertEqual(
            result,
            "❌ Failed to set reminder. Check the time and timezone.",
        )

    async def test_past_followup_is_not_scheduled(self):
        with patch(
            "src.tasks.tasks.followup_after_event.apply_async"
        ) as apply_async:
            result = await create_followup(
                tg_id=1,
                event_title="past event",
                followup_at="2000-01-01T00:00:00+00:00",
            )

        self.assertIn("is in the past", result)
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


if __name__ == "__main__":
    unittest.main()
