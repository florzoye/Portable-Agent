import logging
from typing import Optional, Union
from datetime import datetime, timedelta, timezone

from src.models.events import EventModel
from src.enum.timeframe import TimeFrame
from src.services.calendar.creds_manager import CredentialsManager
from db.database_protocol import UsersBase, GoogleTokensBase
from utils.helpers import preprocess_event_data

class CalendarService:
    def __init__(
        self,
        users_repo: UsersBase,
        token_repo: GoogleTokensBase,
        credentials_manager: CredentialsManager
    ):
        self.users_repo = users_repo
        self.token_repo = token_repo
        self.credentials_manager = credentials_manager
        self.logger = logging.getLogger(self.__class__.__name__)

    async def _get_user(self, tg_id: int):
        return await self.users_repo.get_user_by_tg_id(tg_id)

    async def get_events(
        self,
        tg_id: int,
        days_ahead: Optional[Union[TimeFrame, int]] = TimeFrame.WEEK
    ) -> list[EventModel]:
        user = await self._get_user(tg_id)
        service = await self.credentials_manager.get_service(user.id)

        now = datetime.now(timezone.utc)
        days = days_ahead if isinstance(days_ahead, int) else days_ahead.value
        time_max = now + timedelta(days=days)

        result: dict = await self.credentials_manager._run_sync(
            service.events().list(
                calendarId="primary",
                timeMin=now.isoformat(),
                timeMax=time_max.isoformat(),
                singleEvents=True,
                orderBy="startTime"
            ).execute
        )

        self.logger.info(f"Fetched events for tg_id={tg_id}, days_ahead={days_ahead}")
        return preprocess_event_data(result.get("items", []))