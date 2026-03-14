import re
from typing import Any, Optional
from datetime import timezone, datetime

from src.models import EventModel
from utils.const import GOOGLE_CALENDAR_REDIRECT_URI

def preprocess_event_data(raw_events: list[dict[str, Any]]) -> list[EventModel]:
    return [EventModel.model_validate(event) for event in raw_events]

def format_event(e: dict) -> str:
    start = e.get("start") or {}
    end = e.get("end") or {}
    start_time = start.get("dateTime") or start.get("date", "—")
    end_time = end.get("dateTime") or end.get("date", "—")

    return (
        f"\n🔹 {e.get('summary', '—')}"
        f"\n   ID: {e.get('id')}"
        f"\n   Начало: {start_time}"
        f"\n   Конец: {end_time}"
        + (f"\n   Место: {e.get('location')}" if e.get('location') else "")
        + (f"\n   Описание: {e.get('description')}" if e.get('description') else "")
    )

class DataCreator:
    @staticmethod
    def get_flow_web_config(
        client_id: str, 
        client_secret: str
    ) -> dict:
        return {
            "web": {
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                    "redirect_uris": [GOOGLE_CALENDAR_REDIRECT_URI]
            }
        }

    @staticmethod
    def credentials_dict(
        token_data: Any,
        client_id: str, 
        client_secret: str
    ) -> dict:
        return {
            "token": token_data.access_token,
            "refresh_token": token_data.refresh_token,
            "token_uri": "https://oauth2.googleapis.com/token",
            "client_id": client_id,
            "client_secret": client_secret,
        }

class DateTimeNormalizer:
    @staticmethod
    def normalize_expiry_for_db(expiry: Optional[datetime]) -> Optional[datetime]:
        """aware → naive UTC before saving to the database"""
        if expiry and expiry.tzinfo is not None:
            return expiry.replace(tzinfo=None)
        return expiry

    @staticmethod
    def normalize_expiry_from_db(expiry: Optional[datetime]) -> Optional[datetime]:
        """naive → aware UTC when reading from the database"""
        if expiry and expiry.tzinfo is None:
            return expiry.replace(tzinfo=timezone.utc)
        return expiry

def _md_to_html(text: str) -> str:
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    text = re.sub(
        r"```(?:\w+)?\n?([\s\S]*?)```",
        lambda m: f"<pre><code>{m.group(1).strip()}</code></pre>",
        text,
    )
    text = re.sub(r"`([^`\n]+)`", r"<code>\1</code>", text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text, flags=re.DOTALL)
    text = re.sub(r"__(.+?)__", r"<b>\1</b>", text, flags=re.DOTALL)
    text = re.sub(r"\*([^*\n]+)\*", r"<i>\1</i>", text)
    text = re.sub(r"(?<!\w)_([^_\n]+)_(?!\w)", r"<i>\1</i>", text)
    text = re.sub(r"~~(.+?)~~", r"<s>\1</s>", text)
    text = re.sub(r"^#{1,3} (.+)$", r"<b>\1</b>", text, flags=re.MULTILINE)
    text = re.sub(r"^[\-\*] (.+)$", r"• \1", text, flags=re.MULTILINE)
    text = re.sub(r"^---+$", "─" * 20, text, flags=re.MULTILINE)

    return text.strip()
