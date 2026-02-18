from typing import Any, Optional
from datetime import timezone, datetime

from src.models import EventModel
from utils.const import REDIRECT_URI

def preprocess_event_data(raw_events: list[dict[str, Any]]) -> list[EventModel]:
    return [EventModel.model_validate(event) for event in raw_events]

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
                    "redirect_uris": [REDIRECT_URI]
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
        """aware → naive UTC перед сохранением в БД"""
        if expiry and expiry.tzinfo is not None:
            return expiry.replace(tzinfo=None)
        return expiry

    @staticmethod
    def normalize_expiry_from_db(expiry: Optional[datetime]) -> Optional[datetime]:
        """naive → aware UTC при чтении из БД"""
        if expiry and expiry.tzinfo is None:
            return expiry.replace(tzinfo=timezone.utc)
        return expiry
