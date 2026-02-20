import logging
from typing import Optional, List

from db.sqlite.manager import AsyncDatabaseManager
from db.sqlite.schemas import (
    create_users_indexes_sql,
    create_users_table_sql,
    insert_user_sql,
    update_user_sql,
    select_user_by_tg_id_sql,
    select_user_by_id_sql,
    select_user_by_google_id_sql,
    select_all_users_sql,
    delete_user_sql,
    user_exists_by_tg_id_sql,
    user_exists_by_google_id_sql,
    drop_all_tables_sql,
)
from src.models import UserModel
from db.database_protocol import UsersBase


class UsersSQLite(UsersBase):
    def __init__(self, db: AsyncDatabaseManager):
        self.db = db
        self.logger = logging.getLogger(self.__class__.__name__)

    async def create_tables(self) -> bool:
        try:
            await self.db.execute(create_users_table_sql())
            for index_sql in create_users_indexes_sql():  
                await self.db.execute(index_sql)
            self.logger.info("✅ Таблица users и индексы созданы")
            return True
        except Exception as e:
            self.logger.error(f"❌ Ошибка при создании таблиц: {e}")
            return False

    async def add_user(
        self,
        tg_id: int,
        tg_nick: Optional[str] = None,
        email: Optional[str] = None,
        google_id: Optional[str] = None
    ) -> Optional[UserModel]:
        try:
            existing = await self.get_user_by_tg_id(tg_id)
            if existing:
                self.logger.warning(f"⚠️ Пользователь {tg_id} уже существует")
                return existing

            await self.db.execute(insert_user_sql(), {
                "tg_id": tg_id,
                "tg_nick": tg_nick,
                "email": email,
                "google_id": google_id
            })
            user = await self.get_user_by_tg_id(tg_id)
            self.logger.info(f"✅ Пользователь добавлен: tg_id={tg_id}")
            return user
        except Exception as e:
            self.logger.error(f"❌ Ошибка при добавлении пользователя {tg_id}: {e}", exc_info=True)
            return None

    async def get_user_by_tg_id(self, tg_id: int) -> Optional[UserModel]:
        try:
            row = await self.db.fetchone(select_user_by_tg_id_sql(), {"tg_id": tg_id})
            return self._row_to_user(row) if row else None
        except Exception as e:
            self.logger.error(f"❌ Ошибка при получении пользователя {tg_id}: {e}")
            return None

    async def get_user_by_id(self, user_id: int) -> Optional[UserModel]:
        try:
            row = await self.db.fetchone(select_user_by_id_sql(), {"id": user_id})
            return self._row_to_user(row) if row else None
        except Exception as e:
            self.logger.error(f"❌ Ошибка при получении пользователя id={user_id}: {e}")
            return None

    async def get_user_by_google_id(self, google_id: str) -> Optional[UserModel]:
        try:
            row = await self.db.fetchone(select_user_by_google_id_sql(), {"google_id": google_id})
            return self._row_to_user(row) if row else None
        except Exception as e:
            self.logger.error(f"❌ Ошибка при получении пользователя google_id={google_id}: {e}")
            return None

    async def get_all_users(self) -> List[UserModel]:
        try:
            rows = await self.db.fetchall(select_all_users_sql())
            return [self._row_to_user(row) for row in rows]
        except Exception as e:
            self.logger.error(f"❌ Ошибка при получении всех пользователей: {e}")
            return []

    async def user_exists(self, tg_id: int) -> bool:
        try:
            row = await self.db.fetchone(user_exists_by_tg_id_sql(), {"tg_id": tg_id})
            return row is not None
        except Exception as e:
            self.logger.error(f"❌ Ошибка при проверке существования пользователя {tg_id}: {e}")
            return False

    async def google_id_exists(self, google_id: str) -> bool:
        try:
            row = await self.db.fetchone(user_exists_by_google_id_sql(), {"google_id": google_id})
            return row is not None
        except Exception as e:
            self.logger.error(f"❌ Ошибка при проверке google_id: {e}")
            return False

    async def update_user(
        self,
        tg_id: int,
        tg_nick: Optional[str] = None,
        email: Optional[str] = None,
        google_id: Optional[str] = None
    ) -> bool:
        try:
            current_user = await self.get_user_by_tg_id(tg_id)
            if not current_user:
                self.logger.warning(f"⚠️ Пользователь {tg_id} не найден для обновления")
                return False

            await self.db.execute(update_user_sql(), {
                "tg_id": tg_id,
                "tg_nick": tg_nick if tg_nick is not None else current_user.tg_nick,
                "email": email if email is not None else current_user.email,
                "google_id": google_id if google_id is not None else current_user.google_id
            })
            self.logger.info(f"✅ Пользователь обновлен: tg_id={tg_id}")
            return True
        except Exception as e:
            self.logger.error(f"❌ Ошибка при обновлении пользователя {tg_id}: {e}", exc_info=True)
            return False

    async def delete_user(self, tg_id: int) -> bool:
        try:
            await self.db.execute(delete_user_sql(), {"tg_id": tg_id})
            self.logger.info(f"✅ Пользователь удален: tg_id={tg_id}")
            return True
        except Exception as e:
            self.logger.error(f"❌ Ошибка при удалении пользователя {tg_id}: {e}")
            return False

    async def delete_all_tables(self) -> bool:
        try:
            await self.db.execute(drop_all_tables_sql())
            self.logger.info("✅ Все таблицы удалены")
            return True
        except Exception as e:
            self.logger.error(f"❌ Ошибка при удалении таблиц: {e}")
            return False

    def _row_to_user(self, row: dict) -> UserModel:
        return UserModel(
            id=row["id"],
            tg_id=row["tg_id"],
            tg_nick=row.get("tg_nick"),
            email=row.get("email"),
            google_id=row.get("google_id"),
            created_at=row.get("created_at"),
            updated_at=row.get("updated_at")
        )