import json
import logging
from typing import Optional
from datetime import datetime
from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import TokenModel
from db.database_protocol import GoogleTokensBase
from db.sqlalchemy.models import GoogleToken, Users

class GoogleTokensORM(GoogleTokensBase):
    def __init__(self, session: AsyncSession):
        self.session = session
        self.logger = logging.getLogger(self.__class__.__name__)

    async def create_tables(self) -> bool:
        ...

    async def save_token(
        self,
        user_id: int,
        access_token: str,
        refresh_token: Optional[str] = None,
        token_type: str = "Bearer",
        token_expiry: Optional[datetime] = None,
        scopes: Optional[str] = None
    ) -> bool:
        try:
            existing_token = await self.get_token(user_id)

            if existing_token:
                return await self._update_token_by_id(
                    token_id=existing_token.id,
                    access_token=access_token,
                    refresh_token=refresh_token,
                    token_expiry=token_expiry
                )
            else:
                token = GoogleToken(
                    user_id=user_id,
                    access_token=access_token,
                    refresh_token=refresh_token,
                    token_expiry=token_expiry,
                    token_type=token_type,
                    scopes=json.dumps(scopes) if scopes is not None else None
                )
                self.session.add(token)
                await self.session.flush()
                self.logger.info(f"✅ Токен для пользователя {user_id} успешно сохранен")
                return True

        except Exception as e:
            self.logger.error(f"❌ Ошибка при сохранении токена для пользователя {user_id}: {e}", exc_info=True)
            return False

    async def get_token(self, user_id: int) -> Optional[TokenModel]:
        try:
            result = await self.session.execute(
                select(GoogleToken)
                .where(GoogleToken.user_id == user_id)
                .order_by(GoogleToken.created_at.desc())
                .limit(1)
            )
            token = result.scalar_one_or_none()
            return TokenModel.model_validate(token) if token else None
        except Exception as e:
            self.logger.error(f"❌ Ошибка при получении токена для пользователя {user_id}: {e}")
            return None

    async def get_token_by_tg_id(self, tg_id: int) -> Optional[TokenModel]:
        try:
            result = await self.session.execute(
                select(GoogleToken)
                .join(Users, GoogleToken.user_id == Users.id)  
                .where(Users.tg_id == tg_id)
                .order_by(GoogleToken.created_at.desc())
                .limit(1)
            )
            token = result.scalar_one_or_none()
            return TokenModel.model_validate(token) if token else None
        except Exception as e:
            self.logger.error(f"❌ Ошибка при получении токена по tg_id {tg_id}: {e}")
            return None

    async def update_token(
        self,
        user_id: int,
        access_token: Optional[str] = None,
        refresh_token: Optional[str] = None,
        token_expiry: Optional[datetime] = None
    ) -> bool:
        try:
            token = await self.get_token(user_id)
            if not token:
                self.logger.warning(f"⚠️ Токен для пользователя {user_id} не найден")
                return False
            return await self._update_token_by_id(token.id, access_token, refresh_token, token_expiry)
        except Exception as e:
            self.logger.error(f"❌ Ошибка при обновлении токена для пользователя {user_id}: {e}", exc_info=True)
            return False

    async def _update_token_by_id(
        self,
        token_id: int,
        access_token: Optional[str] = None,
        refresh_token: Optional[str] = None,
        token_expiry: Optional[datetime] = None
    ) -> bool:
        try:
            update_data: dict = {"updated_at": datetime.now()}
            if access_token is not None:
                update_data["access_token"] = access_token
            if refresh_token is not None:
                update_data["refresh_token"] = refresh_token
            if token_expiry is not None:
                update_data["token_expiry"] = token_expiry

            await self.session.execute(
                update(GoogleToken)
                .where(GoogleToken.id == token_id)
                .values(**update_data)
            )
            self.logger.info(f"✅ Токен id={token_id} успешно обновлен")
            return True
        except Exception as e:
            self.logger.error(f"❌ Ошибка при обновлении токена id={token_id}: {e}", exc_info=True)
            return False

    async def delete_token(self, user_id: int) -> bool:
        try:
            await self.session.execute(
                delete(GoogleToken).where(GoogleToken.user_id == user_id)
            )
            self.logger.info(f"✅ Токен пользователя {user_id} удален")
            return True
        except Exception as e:
            self.logger.error(f"❌ Ошибка при удалении токена пользователя {user_id}: {e}")
            return False

    async def token_exists(self, user_id: int) -> bool:
        try:
            result = await self.session.execute(
                select(GoogleToken.id)
                .where(GoogleToken.user_id == user_id)
                .limit(1)
            )
            return result.scalar_one_or_none() is not None
        except Exception as e:
            self.logger.error(f"❌ Ошибка при проверке существования токена для пользователя {user_id}: {e}")
            return False

    async def delete_all_tables(self) -> bool:
        ...