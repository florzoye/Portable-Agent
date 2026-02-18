from datetime import datetime
from typing import Any, Optional

from src.models import TokenModel
from utils.helpers import DateTimeNormalizer
from db.database_protocol import GoogleTokensBase

class TokenService:
    def __init__(self, tokens_repo: GoogleTokensBase):
        self.tokens_repo = tokens_repo

    async def get_token(self, user_id: int) -> Optional[TokenModel]:
        return await self.tokens_repo.get_token(user_id)

    async def save_token(self, user_id: int, access_token: str, refresh_token: Optional[str],
                         expiry: Optional[datetime], scopes: Any) -> bool:
        return await self.tokens_repo.save_token(
            user_id=user_id,
            access_token=access_token,
            refresh_token=refresh_token,
            token_expiry=DateTimeNormalizer.normalize_expiry_for_db(expiry),
            scopes=scopes,
        )

    async def update_token(self, user_id: int, access_token: str,
                           refresh_token: Optional[str], expiry: Optional[datetime]) -> bool:
        return await self.tokens_repo.update_token(
            user_id=user_id,
            access_token=access_token,
            refresh_token=refresh_token,
            token_expiry=DateTimeNormalizer.normalize_expiry_for_db(expiry),
        )

    async def delete_token(self, user_id: int) -> bool:
        return await self.tokens_repo.delete_token(user_id)

    async def token_exists(self, user_id: int) -> bool:
        return await self.tokens_repo.token_exists(user_id)