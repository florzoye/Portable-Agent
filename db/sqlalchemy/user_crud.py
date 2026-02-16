import logging
from typing import Optional, List
from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession

from db.database_protocol import UsersBase
from db.sqlalchemy.models import Base, Users


class UsersORM(UsersBase):
    def __init__(self, session: AsyncSession):
        self.session = session
        self.logger = logging.getLogger(self.__class__.__name__)
    
    async def create_tables(self) -> bool:
        try:
            async with self.session.begin():
                await self.session.run_sync(Base.metadata.create_all)
            self.logger.info("✅ Таблицы успешно созданы")
            return True
        except Exception as e:
            self.logger.error(f"❌ Ошибка при создании таблиц: {e}", exc_info=True)
            return False

    async def add_user(
        self,
        tg_id: int,
        tg_nick: Optional[str] = None,
        email: Optional[str] = None,
        google_id: Optional[str] = None
    ) -> Optional[Users]:
        try:
            user = Users(
                tg_id=tg_id,
                tg_nick=tg_nick,
                email=email,
                google_id=google_id
            )
            self.session.add(user)
            await self.session.flush()
            await self.session.refresh(user)
            self.logger.info(f"✅ Пользователь {tg_id} успешно добавлен")
            return user
        except Exception as e:
            self.logger.error(f"❌ Ошибка при добавлении пользователя {tg_id}: {e}", exc_info=True)
            return None

    async def get_user_by_tg_id(self, tg_id: int) -> Optional[Users]:
        try:
            result = await self.session.execute(
                select(Users).where(Users.tg_id == tg_id)
            )
            user = result.scalar_one_or_none()
            return user
        except Exception as e:
            self.logger.error(f"❌ Ошибка при получении пользователя {tg_id}: {e}")
            return None

    async def get_user_by_id(self, user_id: int) -> Optional[Users]:
        try:
            result = await self.session.execute(
                select(Users).where(Users.id == user_id)
            )
            user = result.scalar_one_or_none()
            return user
        except Exception as e:
            self.logger.error(f"❌ Ошибка при получении пользователя с ID {user_id}: {e}")
            return None

    async def get_user_by_google_id(self, google_id: str) -> Optional[Users]:
        try:
            result = await self.session.execute(
                select(Users).where(Users.google_id == google_id)
            )
            user = result.scalar_one_or_none()
            return user
        except Exception as e:
            self.logger.error(f"❌ Ошибка при получении пользователя с google_id {google_id}: {e}")
            return None

    async def get_all_users(self) -> List[Users]:
        try:
            result = await self.session.execute(select(Users))
            users = result.scalars().all()
            return list(users)
        except Exception as e:
            self.logger.error(f"❌ Ошибка при получении всех пользователей: {e}")
            return []

    async def user_exists(self, tg_id: int) -> bool:
        try:
            result = await self.session.execute(
                select(Users.id).where(Users.tg_id == tg_id).limit(1)
            )
            return result.scalar_one_or_none() is not None
        except Exception as e:
            self.logger.error(f"❌ Ошибка при проверке существования пользователя {tg_id}: {e}")
            return False

    async def google_id_exists(self, google_id: str) -> bool:
        try:
            result = await self.session.execute(
                select(Users.id).where(Users.google_id == google_id).limit(1)
            )
            return result.scalar_one_or_none() is not None
        except Exception as e:
            self.logger.error(f"❌ Ошибка при проверке существования google_id {google_id}: {e}")
            return False

    async def update_user(
        self,
        tg_id: int,
        tg_nick: Optional[str] = None,
        email: Optional[str] = None,
        google_id: Optional[str] = None
    ) -> bool:
        try:
            # Получаем текущего пользователя
            user = await self.get_user_by_tg_id(tg_id)
            if not user:
                self.logger.warning(f"⚠️ Пользователь {tg_id} не найден для обновления")
                return False
            
            # Формируем словарь для обновления
            update_data = {}
            if tg_nick is not None:
                update_data["tg_nick"] = tg_nick
            if email is not None:
                update_data["email"] = email
            if google_id is not None:
                update_data["google_id"] = google_id
            
            if not update_data:
                return True
            
            await self.session.execute(
                update(Users).where(Users.tg_id == tg_id).values(**update_data)
            )
            self.logger.info(f"✅ Пользователь {tg_id} успешно обновлен")
            return True
        except Exception as e:
            self.logger.error(f"❌ Ошибка при обновлении пользователя {tg_id}: {e}")
            return False

    async def delete_user(self, tg_id: int) -> bool:
        try:
            await self.session.execute(
                delete(Users).where(Users.tg_id == tg_id)
            )
            self.logger.info(f"✅ Пользователь {tg_id} удален")
            return True
        except Exception as e:
            self.logger.error(f"❌ Ошибка при удалении пользователя {tg_id}: {e}")
            return False
    
    async def delete_all_tables(self) -> bool:
        try:
            async with self.session.begin():
                await self.session.run_sync(Base.metadata.drop_all)
            self.logger.info("✅ Все таблицы удалены")
            return True
        except Exception as e:
            self.logger.error(f"❌ Ошибка при удалении всех таблиц: {e}", exc_info=True)
            return False