from data import get_config
from src.enum import DatabaseType
from src.services.calendar.google_calendar import GoogleCalendarService
from db.database_protocol import UsersBase, GoogleTokensBase

class ServiceFactory:
    @staticmethod
    async def create_google_calendar_service(session) -> GoogleCalendarService:
        cfg = get_config()

        from db.sqlalchemy.user_crud import UsersORM
        from db.sqlalchemy.google_crud import GoogleTokensORM
        users_repo = UsersORM(session)
        tokens_repo = GoogleTokensORM(session)

        return GoogleCalendarService(
            users_repo=users_repo,
            tokens_repo=tokens_repo,
            client_id=cfg.GOOGLE_CONFIG.GOOGLE_CLIENT_ID,
            client_secret=cfg.GOOGLE_CONFIG.GOOGLE_CLIENT_SECRET,
        )

    @staticmethod
    def create_users_repo(session) -> UsersBase:
        from db.sqlalchemy.user_crud import UsersORM
        return UsersORM(session)
    
    @staticmethod
    def create_tokens_repo(session) -> GoogleTokensBase:
        from db.sqlalchemy.google_crud import GoogleTokensORM
        return GoogleTokensORM(session)