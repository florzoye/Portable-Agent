import logging
from typing import Optional, Union
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession
from db.sqlite.manager import AsyncDatabaseManager
from db.database_protocol import UsersBase, GoogleTokensBase

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

        if self.db_type == "sqlite":
            await self._setup_sqlite(DB_CONFIG)
        elif self.db_type == "postgresql":
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
        from db.sqlalchemy.session import SQLAlchemyManager

        self.sqlalchemy_manager = SQLAlchemyManager()
        self.sqlalchemy_manager.init()
        self.logger.debug("PostgreSQL manager initialized")

    def get_session(self) -> Union[AsyncDatabaseManager, AsyncSession]:
        if not self._initialized:
            raise RuntimeError("Database not initialized. Call await database.setup() first")

        if self.db_type == "sqlite":
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
        """Создать все таблицы"""
        session = self.get_session()
        
        users_repo = self.get_users_repo(session)
        tokens_repo = self.get_tokens_repo(session)
        
        await users_repo.create_tables()
        
        if self.db_type == "sqlite":
            await tokens_repo.create_tables()
        
        self.logger.info("✅ All tables created")

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


