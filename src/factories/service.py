from data.init_configs import get_config
from src.enum.db import DatabaseType
from src.services.calendar.google_calendar import GoogleCalendarService
from db.database_protocol import UsersBase, GoogleTokensBase

class ServiceFactory:
    @staticmethod
    async def create_google_calendar_service(session) -> GoogleCalendarService:
        cfg = get_config()

        if cfg.DB_CONFIG.DB_TYPE.lower() == DatabaseType.SQLITE.value:
            from db.sqlite.user_crud import UsersSQLite
            from db.sqlite.google_crud import TokensSQLite
            users_repo = UsersSQLite(session)
            tokens_repo = TokensSQLite(session)
        else:
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
        cfg = get_config()
        if cfg.DB_CONFIG.DB_TYPE.lower() == DatabaseType.SQLITE.value:
            from db.sqlite.user_crud import UsersSQLite
            return UsersSQLite(session)
        from db.sqlalchemy.user_crud import UsersORM
        return UsersORM(session)

    @staticmethod
    def create_tokens_repo(session) -> GoogleTokensBase:
        cfg = get_config()
        if cfg.DB_CONFIG.DB_TYPE.lower() == DatabaseType.SQLITE.value:
            from db.sqlite.google_crud import TokensSQLite
            return TokensSQLite(session)
        from db.sqlalchemy.google_crud import GoogleTokensORM
        return GoogleTokensORM(session)