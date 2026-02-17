import logging
from typing import Optional, Union
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from db.sqlalchemy.models import Base
from db.sqlite.manager import AsyncDatabaseManager
from db.database_protocol import UsersBase, GoogleTokensBase

from src.enum.db import DatabaseType
from src.factories.repository_factory import repository_factory

class Database:
    def __init__(self):
        self.sqlalchemy_manager = None
        self.sqlite_manager = None
        self.db_type: Optional[str] = None
        self._initialized = False
        self.logger = logging.getLogger(self.__class__.__name__)

    async def setup(self):
        from data.init_configs import get_config
        DB_CONFIG = get_config().DB_CONFIG

        self.db_type = DB_CONFIG.DB_TYPE

        if self.db_type == DatabaseType.SQLITE.value:
            await self._setup_sqlite(DB_CONFIG)
        elif self.db_type == DatabaseType.POSTGRESQL.value:
            await self._setup_postgresql(DB_CONFIG)
        else:
            raise ValueError(f"Unsupported DB_TYPE: {self.db_type}")

        self._initialized = True
        self.logger.info(f"✅ Database setup complete: {self.db_type}")

    async def _setup_sqlite(self, DB_CONFIG):
        from db.sqlite.manager import AsyncDatabaseManager

        self.sqlite_manager = AsyncDatabaseManager(DB_CONFIG.SQLITE_PATH)
        await self.sqlite_manager.connect()
        self.logger.debug(f"SQLite connected: {DB_CONFIG.SQLITE_PATH}")

    async def _setup_postgresql(self, DB_CONFIG):
        from db.sqlalchemy.session import sqlalchemy_manager

        self.sqlalchemy_manager = sqlalchemy_manager
        self.sqlalchemy_manager.init()
        self.logger.debug("PostgreSQL manager initialized")

    def get_session(self) -> Union[AsyncDatabaseManager, AsyncSession]:
        if not self._initialized:
            raise RuntimeError("Database not initialized. Call await database.setup() first")

        if self.db_type == DatabaseType.SQLITE.value:
            return self.sqlite_manager
        else:
            return self.sqlalchemy_manager.get_session()

    @asynccontextmanager
    async def transaction(self):
        session = self.get_session()
        try:
            yield session  
            if isinstance(session, AsyncSession):
                await session.commit()
         
        except Exception as e:
            if isinstance(session, AsyncSession):
                await session.rollback()
            self.logger.error(f"Transaction error: {e}", exc_info=True)
            raise
        finally:
            if isinstance(session, AsyncSession):
                await session.close()

    def get_users_repo(
        self, 
        session: Optional[Union[AsyncDatabaseManager, AsyncSession]] = None
    ) -> UsersBase:
       
        if session is None:
            session = self.get_session()
        
        return repository_factory.create_users_repo(session)

    def get_tokens_repo(
        self, 
        session: Optional[Union[AsyncDatabaseManager, AsyncSession]] = None
    ) -> GoogleTokensBase:
        if session is None:
            session = self.get_session()
        
        return repository_factory.create_tokens_repo(session)

    async def create_tables(self):
        if not self._initialized:
            raise RuntimeError("Database not initialized")
        
        if self.db_type == DatabaseType.SQLITE.value:
            async with self.transaction() as session:
                session = self.get_session()
                users_repo = self.get_users_repo(session)
                tokens_repo = self.get_tokens_repo(session)

                await users_repo.create_tables()
                await tokens_repo.create_tables()

        elif self.db_type == DatabaseType.POSTGRESQL.value:
            engine = self.sqlalchemy_manager.get_engine()

            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)

        self.logger.info("✅ All tables created")
    
    async def drop_tables(self):
        if not self._initialized:
            raise RuntimeError("Database not initialized")
        
        if self.db_type == DatabaseType.POSTGRESQL.value:
            engine = self.sqlalchemy_manager.get_engine()

            async with engine.begin() as conn:
                await conn.execute(text("DROP SCHEMA public CASCADE"))
                await conn.execute(text("CREATE SCHEMA public"))

            self.logger.info("✅ Database schema fully reset")
        else:
            async with self.transaction() as session:
                tokens_repo = self.get_tokens_repo(session)

                await tokens_repo.delete_all_tables()
            self.logger.info("✅ Database schema fully reset")

    async def close(self):
        if self.sqlite_manager:
            await self.sqlite_manager.close()

        if self.sqlalchemy_manager:
            await self.sqlalchemy_manager.close()
        
        self.logger.info("✅ Database connections closed")

    @property
    def is_initialized(self) -> bool:
        return self._initialized


database = Database()


