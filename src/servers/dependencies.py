from db.database import database
from src.factories import ServiceFactory
from src.exceptions import CalendarServiceException, UserRepositoryException, TokenRepositoryException

async def get_calendar_service():
    try:
        async with database.transaction() as session:
            service = await ServiceFactory.create_google_calendar_service(session)
            yield service
    except CalendarServiceException:
        raise
    except Exception as exp:
        raise CalendarServiceException(original_error=exp)


async def get_users_repo():
    try:
        async with database.transaction() as session:
            yield ServiceFactory.create_users_repo(session)
    except UserRepositoryException:
        raise
    except Exception as exp:
        raise UserRepositoryException(original_error=exp)


async def get_tokens_repo():
    try:
        async with database.transaction() as session:
            yield ServiceFactory.create_tokens_repo(session)
    except TokenRepositoryException:
        raise
    except Exception as exp:
        raise TokenRepositoryException(original_error=exp)