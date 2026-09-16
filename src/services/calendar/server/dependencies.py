from collections.abc import AsyncIterator

from fastapi import HTTPException
from sqlalchemy.exc import SQLAlchemyError

from db.database import Database
from db.database_protocol import GoogleTokensBase, UsersBase
from src.exceptions.services_exp import CalendarServiceException
from src.exceptions.repo_exp import TokenRepositoryException, UserRepositoryException
from src.factories import ServiceFactory
from src.services.calendar.google_calendar import GoogleCalendarService


class CalendarDependencyProvider:
    """Application-composed FastAPI dependencies for calendar routes."""

    def __init__(self, database: Database):
        self.database = database

    async def calendar_service(self) -> AsyncIterator[GoogleCalendarService]:
        async with self.database.transaction() as session:
            try:
                yield await ServiceFactory.create_google_calendar_service(session)
            except HTTPException:
                raise
            except CalendarServiceException:
                raise
            except (OSError, TimeoutError, ValueError, SQLAlchemyError) as exp:
                raise CalendarServiceException(original_error=exp)

    async def users_repo(self) -> AsyncIterator[UsersBase]:
        async with self.database.transaction() as session:
            try:
                yield ServiceFactory.create_users_repo(session)
            except HTTPException:
                raise
            except UserRepositoryException:
                raise
            except (OSError, TimeoutError, ValueError, SQLAlchemyError) as exp:
                raise UserRepositoryException(original_error=exp)

    async def tokens_repo(self) -> AsyncIterator[GoogleTokensBase]:
        async with self.database.transaction() as session:
            try:
                yield ServiceFactory.create_tokens_repo(session)
            except HTTPException:
                raise
            except TokenRepositoryException:
                raise
            except (OSError, TimeoutError, ValueError, SQLAlchemyError) as exp:
                raise TokenRepositoryException(original_error=exp)


_provider: CalendarDependencyProvider | None = None


def configure_dependencies(database: Database) -> None:
    global _provider
    _provider = CalendarDependencyProvider(database)


def _configured() -> CalendarDependencyProvider:
    if _provider is None:
        raise RuntimeError("Calendar dependencies are not configured")
    return _provider


async def get_calendar_service():
    async for service in _configured().calendar_service():
        yield service


async def get_users_repo():
    async for repository in _configured().users_repo():
        yield repository


async def get_tokens_repo():
    async for repository in _configured().tokens_repo():
        yield repository
