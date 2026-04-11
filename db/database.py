import logging
from typing import Optional
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from db.sqlalchemy.models import Base
from db.database_protocol import UsersBase, GoogleTokensBase

from src.enum import DatabaseType
from src.factories import repository_factory

class Database:
    def __init__(self):
        self.sqlalchemy_manager = None
        self.db_type: Optional[str] = None
        self._initialized = False
        self.logger = logging.getLogger(self.__class__.__name__)

    async def setup(self):
        from data.init_configs import get_config
        DB_CONFIG = get_config().DB_CONFIG
        self.db_type = DB_CONFIG.DB_TYPE

        from db.sqlalchemy.session import sqlalchemy_manager
        self.sqlalchemy_manager = sqlalchemy_manager
        self.sqlalchemy_manager.init()

        self._initialized = True
        self.logger.info(f"✅ Database setup complete: {self.db_type}")

    def get_session(self) -> AsyncSession:
        if not self._initialized:
            raise RuntimeError("Database not initialized")
        return self.sqlalchemy_manager.get_session()

    @asynccontextmanager
    async def transaction(self):
        session = self.get_session()
        try:
            yield session
            await session.commit()
        except Exception as e:
            await session.rollback()
            self.logger.error(f"Transaction error: {e}", exc_info=True)
            raise
        finally:
            await session.close()

    def get_users_repo(self, session: Optional[AsyncSession] = None) -> UsersBase:
        if session is None:
            session = self.get_session()
        return repository_factory.create_users_repo(session)

    def get_tokens_repo(self, session: Optional[AsyncSession] = None) -> GoogleTokensBase:
        if session is None:
            session = self.get_session()
        return repository_factory.create_tokens_repo(session)

    async def create_tables(self):
        if not self._initialized:
            raise RuntimeError("Database not initialized")
        engine = self.sqlalchemy_manager.get_engine()
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        self.logger.info("✅ All tables created")

    async def drop_tables(self):
        if not self._initialized:
            raise RuntimeError("Database not initialized")
        engine = self.sqlalchemy_manager.get_engine()

        if self.db_type == DatabaseType.POSTGRESQL:
            async with engine.begin() as conn:
                await conn.execute(text("DROP SCHEMA public CASCADE"))
                await conn.execute(text("CREATE SCHEMA public"))
        else:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.drop_all)

        self.logger.info("✅ All tables dropped")

    async def close(self):
        if self.sqlalchemy_manager:
            await self.sqlalchemy_manager.close()
        self.logger.info("✅ Database connections closed")

    @property
    def is_initialized(self) -> bool:
        return self._initialized


global_db_manager = Database()


