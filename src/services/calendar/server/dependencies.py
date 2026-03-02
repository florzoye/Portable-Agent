from fastapi import HTTPException
from db.database import global_db_manager
from src.factories import ServiceFactory
from src.exceptions import CalendarServiceException, UserRepositoryException, TokenRepositoryException

async def get_calendar_service():
    async with global_db_manager.transaction() as session:
        try:
            service = await ServiceFactory.create_google_calendar_service(session)
            yield service
        except HTTPException:
            raise
        except CalendarServiceException:
            raise
        except Exception as exp:
            raise CalendarServiceException(original_error=exp)

async def get_users_repo():
    async with global_db_manager.transaction() as session:
        try:
            yield ServiceFactory.create_users_repo(session)
        except HTTPException:
            raise
        except UserRepositoryException:
            raise
        except Exception as exp:
            raise UserRepositoryException(original_error=exp)

async def get_tokens_repo():
    async with global_db_manager.transaction() as session:
        try:
            yield ServiceFactory.create_tokens_repo(session)
        except HTTPException:
            raise
        except TokenRepositoryException:
            raise
        except Exception as exp:
            raise TokenRepositoryException(original_error=exp)