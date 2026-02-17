import logging
from typing import Union
from sqlalchemy.ext.asyncio import AsyncSession

from db.database_protocol import UsersBase, GoogleTokensBase
from db.sqlite.manager import AsyncDatabaseManager


class RepositoryFactory:
    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)
    
    def create_users_repo(
        self, 
        session: Union[AsyncDatabaseManager, AsyncSession]
    ) -> UsersBase:
        if isinstance(session, AsyncDatabaseManager):
            from db.sqlite.user_crud import UsersSQLite
            self.logger.debug("Creating SQLite users repository")
            return UsersSQLite(session)
        elif isinstance(session, AsyncSession):
            from db.sqlalchemy.user_crud import UsersORM
            self.logger.debug("Creating PostgreSQL users repository")
            return UsersORM(session)
        else:
            raise TypeError(
                f"Unsupported session type: {type(session)}. "
                f"Expected AsyncDatabaseManager or AsyncSession"
            )
    
    def create_tokens_repo(
        self, 
        session: Union[AsyncDatabaseManager, AsyncSession]
    ) -> GoogleTokensBase:
        if isinstance(session, AsyncDatabaseManager):
            from db.sqlite.google_crud import TokensSQLite
            self.logger.debug("Creating SQLite tokens repository")
            return TokensSQLite(session)
        elif isinstance(session, AsyncSession):
            from db.sqlalchemy.google_crud import GoogleTokensORM
            self.logger.debug("Creating PostgreSQL tokens repository")
            return GoogleTokensORM(session)
        else:
            raise TypeError(
                f"Unsupported session type: {type(session)}. "
                f"Expected AsyncDatabaseManager or AsyncSession"
            )


repository_factory = RepositoryFactory()