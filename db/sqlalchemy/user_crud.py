import logging
from typing import Optional, List
from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import UserModel
from db.sqlalchemy.models import  Users
from db.database_protocol import UsersBase

class UsersORM(UsersBase):
    def __init__(self, session: AsyncSession):
        self.session = session
        self.logger = logging.getLogger(self.__class__.__name__)
    
    async def create_tables(self) -> bool:
       ...

    async def add_user(
        self,
        tg_id: int,
        tg_nick: Optional[str] = None,
        email: Optional[str] = None,
        google_id: Optional[str] = None
    ) -> Optional[UserModel]:
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
            self.logger.info(f"✅ User {tg_id} has been successfully added")
            return UserModel.model_validate(user)
        
        except Exception as e:
            self.logger.error(f"❌ Error when adding a user {tg_id}: {e}", exc_info=True)
            return None

    async def get_user_by_tg_id(self, tg_id: int) -> Optional[UserModel]:
        try:
            result = await self.session.execute(
                select(Users).where(Users.tg_id == tg_id)
            )
            user = result.scalar_one_or_none()
            return UserModel.model_validate(user) if user else None
        except Exception as e:
            self.logger.error(f"❌ Error when receiving the user {tg_id}: {e}")
            return None

    async def get_user_by_id(self, user_id: int) -> Optional[UserModel]:
        try:
            result = await self.session.execute(
                select(Users).where(Users.id == user_id)
            )
            user = result.scalar_one_or_none()
            return UserModel.model_validate(user) if user else None
        except Exception as e:
            self.logger.error(f"❌ Error when receiving the user с ID {user_id}: {e}")
            return None

    async def get_user_by_google_id(self, google_id: str) -> Optional[Users]:
        try:
            result = await self.session.execute(
                select(Users).where(Users.google_id == google_id)
            )
            user = result.scalar_one_or_none()
            return UserModel.model_validate(user) if user else None
        except Exception as e:
            self.logger.error(f"❌ Error when receiving the user с google_id {google_id}: {e}")
            return None

    async def get_all_users(self) -> List[UserModel]:
        try:
            result = await self.session.execute(select(Users))
            users = result.scalars().all()
            return [UserModel.model_validate(u) for u in users]
        except Exception as e:
            self.logger.error(f"❌Error when receiving the all users: {e}")
            return []

    async def user_exists(self, tg_id: int) -> bool:
        try:
            result = await self.session.execute(
                select(Users.id).where(Users.tg_id == tg_id).limit(1)
            )
            return result.scalar_one_or_none() is not None
        except Exception as e:
            self.logger.error(f"❌ Error checking the user's existence {tg_id}: {e}")
            return False

    async def google_id_exists(self, google_id: str) -> bool:
        try:
            result = await self.session.execute(
                select(Users.id).where(Users.google_id == google_id).limit(1)
            )
            return result.scalar_one_or_none() is not None
        except Exception as e:
            self.logger.error(f"❌Error checking the existence google_id {google_id}: {e}")
            return False

    async def update_user(
        self,
        tg_id: int,
        tg_nick: Optional[str] = None,
        email: Optional[str] = None,
        google_id: Optional[str] = None
    ) -> bool:
        try:
            user = await self.get_user_by_tg_id(tg_id)
            if not user:
                self.logger.warning(f"⚠️ User {tg_id} not found for update")
                return False
            
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
            self.logger.info(f"✅User {tg_id} has been successfully updated")
            return True
        except Exception as e:
            self.logger.error(f"❌Error when updating the user {tg_id}: {e}")
            return False

    async def delete_user(self, tg_id: int) -> bool:
        try:
            await self.session.execute(
                delete(Users).where(Users.tg_id == tg_id)
            )
            self.logger.info(f"✅ User {tg_id} has been deleted")
            return True
        except Exception as e:
            self.logger.error(f"❌ Error when deleting user {tg_id}: {e}")
            return False
    
    async def delete_all_tables(self) -> bool:
        ...