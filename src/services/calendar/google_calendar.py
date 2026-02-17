from db.database_protocol import UsersBase, GoogleTokensBase
from src.services.calendar.token_service import TokenService
from src.services.calendar.creds_manager import CredentialsManager
from src.services.calendar.auth_service import GoogleAuthService
from src.services.calendar.calendar_service import CalendarService

class GoogleCalendarService:
    def __init__(
        self, 
        users_repo: UsersBase, 
        tokens_repo: GoogleTokensBase,
        client_id: str, client_secret: str
    ):
        self.token_service = TokenService(tokens_repo)
        self.credentials_manager = CredentialsManager(client_id, client_secret, self.token_service)
        self.auth = GoogleAuthService(users_repo, self.token_service, self.credentials_manager, client_id, client_secret)
        self.calendar = CalendarService(users_repo, tokens_repo, self.credentials_manager)

    async def get_auth_url(self, tg_id: int) -> str:
        return await self.auth.get_auth_url(tg_id)

    async def exchange_code(self, tg_id: int, code: str) -> bool:
        return await self.auth.exchange_code(tg_id, code)

    async def revoke_access(self, tg_id: int) -> bool:
        return await self.auth.revoke_access(tg_id)

    async def is_authorized(self, tg_id: int) -> bool:
        return await self.auth.is_authorized(tg_id)

    async def load_credentials(self, tg_id: int) -> bool:
        user = await self.auth.users_repo.get_user_by_tg_id(tg_id)
        if not user:
            return False
        return await self.credentials_manager.load_credentials(user.id)

    async def get_events(self, tg_id: int, **kwargs):
        return await self.calendar.get_events(tg_id, **kwargs)