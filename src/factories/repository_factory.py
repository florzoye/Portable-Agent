import logging
from sqlalchemy.ext.asyncio import AsyncSession

from db.database_protocol import UsersBase, GoogleTokensBase


class RepositoryFactory:
    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)
    
    def create_users_repo(
        self, 
        session: AsyncSession
    ) -> UsersBase:
        if isinstance(session, AsyncSession):
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
        session: AsyncSession
    ) -> GoogleTokensBase:
        if isinstance(session, AsyncSession):
            from db.sqlalchemy.google_crud import GoogleTokensORM
            self.logger.debug("Creating PostgreSQL tokens repository")
            return GoogleTokensORM(session)
        else:
            raise TypeError(
                f"Unsupported session type: {type(session)}. "
                f"Expected AsyncDatabaseManager or AsyncSession"
            )


repository_factory = RepositoryFactory()