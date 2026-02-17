from typing import Any, Optional
from datetime import datetime, timezone

from db.database_protocol import GoogleTokensBase
from src.models.token_model import TokenModel

class TokenService:
    def __init__(self, tokens_repo: GoogleTokensBase):
        self.tokens_repo = tokens_repo

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

    async def get_token(self, user_id: int) -> Optional[TokenModel]:
        return await self.tokens_repo.get_token(user_id)

    async def save_token(self, user_id: int, access_token: str, refresh_token: Optional[str],
                         expiry: Optional[datetime], scopes: Any) -> bool:
        return await self.tokens_repo.save_token(
            user_id=user_id,
            access_token=access_token,
            refresh_token=refresh_token,
            token_expiry=self.normalize_expiry_for_db(expiry),
            scopes=scopes,
        )

    async def update_token(self, user_id: int, access_token: str,
                           refresh_token: Optional[str], expiry: Optional[datetime]) -> bool:
        return await self.tokens_repo.update_token(
            user_id=user_id,
            access_token=access_token,
            refresh_token=refresh_token,
            token_expiry=self.normalize_expiry_for_db(expiry),
        )

    async def delete_token(self, user_id: int) -> bool:
        return await self.tokens_repo.delete_token(user_id)

    async def token_exists(self, user_id: int) -> bool:
        return await self.tokens_repo.token_exists(user_id)