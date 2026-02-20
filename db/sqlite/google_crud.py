import json
import logging
from typing import Optional
from datetime import datetime

from db.database_protocol import GoogleTokensBase
from db.sqlite.manager import AsyncDatabaseManager
from db.sqlite.schemas import (
    create_tokens_indexes_sql,
    create_tokens_table_sql,
    insert_token_sql,
    update_token_sql,
    select_token_by_user_id_sql,
    delete_token_by_user_id_sql,
    token_exists_sql,
    select_token_by_tg_id_sql,
    drop_all_tables_sql
)
from src.models import TokenModel


class TokensSQLite(GoogleTokensBase):
    def __init__(self, db: AsyncDatabaseManager):
        self.db = db
        self.logger = logging.getLogger(self.__class__.__name__)

    async def create_tables(self) -> bool:
        try:
            await self.db.execute(create_tokens_table_sql())
            for index_sql in create_tokens_indexes_sql():  
                await self.db.execute(index_sql)
            self.logger.info("✅ Таблица tokens и индексы созданы")
            return True
        except Exception as e:
            self.logger.error(f"❌ Ошибка при создании таблицы tokens: {e}")
            return False

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
            exists = await self.token_exists(user_id)

            params = {
                "user_id": user_id,
                "access_token": access_token,
                "refresh_token": refresh_token,
                "token_type": token_type,
                "token_expiry": token_expiry.isoformat() if token_expiry else None,
                "scopes": json.dumps(scopes) if scopes is not None else None
            }

            if exists:
                await self.db.execute(update_token_sql(), params)
                self.logger.info(f"✅ Токен обновлен для user_id={user_id}")
            else:
                await self.db.execute(insert_token_sql(), params)
                self.logger.info(f"✅ Токен сохранен для user_id={user_id}")

            return True
        except Exception as e:
            self.logger.error(f"❌ Ошибка при сохранении токена для user_id={user_id}: {e}", exc_info=True)
            return False

    async def get_token(self, user_id: int) -> Optional[TokenModel]:
        try:
            row = await self.db.fetchone(select_token_by_user_id_sql(), {"user_id": user_id})
            return self._row_to_token(row) if row else None
        except Exception as e:
            self.logger.error(f"❌ Ошибка при получении токена для user_id={user_id}: {e}")
            return None

    async def get_token_by_tg_id(self, tg_id: int) -> Optional[TokenModel]:
        try:
            row = await self.db.fetchone(select_token_by_tg_id_sql(), {"tg_id": tg_id})
            return self._row_to_token(row) if row else None
        except Exception as e:
            self.logger.error(f"❌ Ошибка при получении токена по tg_id={tg_id}: {e}")
            return None

    async def update_token(
        self,
        user_id: int,
        access_token: Optional[str] = None,
        refresh_token: Optional[str] = None,
        token_expiry: Optional[datetime] = None
    ) -> bool:
        try:
            current_token = await self.get_token(user_id)
            if not current_token:
                self.logger.warning(f"⚠️ Токен для user_id={user_id} не найден")
                return False

            # Обновляем только переданные поля, остальное берём из текущих данных
            await self.db.execute(update_token_sql(), {
                "user_id": user_id,
                "access_token": access_token if access_token is not None else current_token.access_token,
                "refresh_token": refresh_token if refresh_token is not None else current_token.refresh_token,
                "token_type": current_token.token_type,
                "token_expiry": (
                    token_expiry.isoformat() if token_expiry is not None
                    else (current_token.token_expiry.isoformat() if current_token.token_expiry else None)
                ),
                "scopes": current_token.scopes
            })
            self.logger.info(f"✅ Токен обновлен для user_id={user_id}")
            return True
        except Exception as e:
            self.logger.error(f"❌ Ошибка при обновлении токена для user_id={user_id}: {e}", exc_info=True)
            return False

    async def delete_token(self, user_id: int) -> bool:
        try:
            await self.db.execute(delete_token_by_user_id_sql(), {"user_id": user_id})
            self.logger.info(f"✅ Токен удален для user_id={user_id}")
            return True
        except Exception as e:
            self.logger.error(f"❌ Ошибка при удалении токена для user_id={user_id}: {e}")
            return False

    async def token_exists(self, user_id: int) -> bool:
        try:
            row = await self.db.fetchone(token_exists_sql(), {"user_id": user_id})
            return row is not None
        except Exception as e:
            self.logger.error(f"❌ Ошибка при проверке существования токена: {e}")
            return False

    async def delete_all_tables(self) -> bool:
        try:
            await self.db.execute(drop_all_tables_sql())
            self.logger.info("✅ Таблица tokens удалена")
            return True
        except Exception as e:
            self.logger.error(f"❌ Ошибка при удалении таблицы tokens: {e}")
            return False

    def _row_to_token(self, row: dict) -> TokenModel:
        token_expiry = None
        if row.get("token_expiry"):
            try:
                token_expiry = datetime.fromisoformat(row["token_expiry"])
            except (ValueError, TypeError):
                pass

        return TokenModel(
            id=row["id"],
            user_id=row["user_id"],
            access_token=row["access_token"],
            refresh_token=row.get("refresh_token"),
            token_type=row.get("token_type", "Bearer"),
            scopes=row.get("scopes"),
            token_expiry=token_expiry,
            created_at=row.get("created_at"),
            updated_at=row.get("updated_at")
        )