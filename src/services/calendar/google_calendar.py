from typing import Optional
from datetime import datetime

from db.database_protocol import UsersBase, GoogleTokensBase
from src.services.calendar.token_service import TokenService
from src.services.calendar.auth_service import GoogleAuthService
from src.services.calendar.creds_manager import CredentialsManager
from src.services.calendar.calendar_service import CalendarService


class GoogleCalendarService:
    def __init__(
        self,
        users_repo: UsersBase,
        tokens_repo: GoogleTokensBase,
        client_id: str,
        client_secret: str
    ):
        self.token_service = TokenService(tokens_repo)
        self.credentials_manager = CredentialsManager(client_id, client_secret, self.token_service)
        self.auth = GoogleAuthService(users_repo, self.token_service, self.credentials_manager, client_id, client_secret)
        self.calendar = CalendarService(users_repo, tokens_repo, self.credentials_manager)

    #  Auth 

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

    # Events

    async def get_events(self, tg_id: int, **kwargs):
        return await self.calendar.get_events(tg_id, **kwargs)

    async def get_event_by_id(self, tg_id: int, event_id: str):
        return await self.calendar.get_event_by_id(tg_id, event_id)

    async def create_event(
        self,
        tg_id: int,
        title: str,
        start_time: datetime,
        end_time: datetime,
        description: Optional[str] = None,
        location: Optional[str] = None,
        attendees: Optional[list[str]] = None,
        timezone: str = "UTC"
    ) -> dict:
        return await self.calendar.create_event(
            tg_id=tg_id,
            title=title,
            start_time=start_time,
            end_time=end_time,
            description=description,
            location=location,
            attendees=attendees,
            timezone=timezone
        )

    async def update_event(
        self,
        tg_id: int,
        event_id: str,
        title: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        description: Optional[str] = None,
        location: Optional[str] = None,
        timezone: str = "UTC"
    ) -> dict:
        return await self.calendar.update_event(
            tg_id=tg_id,
            event_id=event_id,
            title=title,
            start_time=start_time,
            end_time=end_time,
            description=description,
            location=location,
            timezone=timezone
        )

    async def delete_event(self, tg_id: int, event_id: str) -> bool:
        return await self.calendar.delete_event(tg_id, event_id)

    async def search_events(self, tg_id: int, query: str, days_ahead: int = 30):
        return await self.calendar.search_events(tg_id, query, days_ahead)

    async def get_events_range(self, tg_id: int, start: datetime, end: datetime):
        return await self.calendar.get_events_range(tg_id, start, end)