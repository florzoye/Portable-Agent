import logging
from typing import Optional, Union
from datetime import datetime, timedelta, timezone

from src.enum import TimeFrame
from src.models import EventModel
from src.services.calendar.creds_manager import CredentialsManager

from utils.helpers import preprocess_event_data
from db.database_protocol import UsersBase, GoogleTokensBase

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

    async def get_event_by_id(self, tg_id: int, event_id: str) -> Optional[dict]:
        user = await self._get_user(tg_id)
        service = await self.credentials_manager.get_service(user.id)

        event = await self.credentials_manager._run_sync(
            service.events().get(
                calendarId="primary",
                eventId=event_id
            ).execute
        )
        self.logger.info(f"Fetched event {event_id} for tg_id={tg_id}")
        return event

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
        user = await self._get_user(tg_id)
        service = await self.credentials_manager.get_service(user.id)

        event_body = {
            "summary": title,
            "start": {"dateTime": start_time.isoformat(), "timeZone": timezone},
            "end": {"dateTime": end_time.isoformat(), "timeZone": timezone},
        }

        if description:
            event_body["description"] = description
        if location:
            event_body["location"] = location
        if attendees:
            event_body["attendees"] = [{"email": email} for email in attendees]

        result = await self.credentials_manager._run_sync(
            service.events().insert(
                calendarId="primary",
                body=event_body
            ).execute
        )
        self.logger.info(f"Created event '{title}' for tg_id={tg_id}")
        return result

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
        user = await self._get_user(tg_id)
        service = await self.credentials_manager.get_service(user.id)

        current = await self.credentials_manager._run_sync(
            service.events().get(
                calendarId="primary",
                eventId=event_id
            ).execute
        )

        if title:
            current["summary"] = title
        if description is not None:
            current["description"] = description
        if location is not None:
            current["location"] = location
        if start_time:
            current["start"] = {"dateTime": start_time.isoformat(), "timeZone": timezone}
        if end_time:
            current["end"] = {"dateTime": end_time.isoformat(), "timeZone": timezone}

        result = await self.credentials_manager._run_sync(
            service.events().update(
                calendarId="primary",
                eventId=event_id,
                body=current
            ).execute
        )
        self.logger.info(f"Updated event {event_id} for tg_id={tg_id}")
        return result

    async def delete_event(self, tg_id: int, event_id: str) -> bool:
        user = await self._get_user(tg_id)
        service = await self.credentials_manager.get_service(user.id)

        await self.credentials_manager._run_sync(
            service.events().delete(
                calendarId="primary",
                eventId=event_id
            ).execute
        )
        self.logger.info(f"Deleted event {event_id} for tg_id={tg_id}")
        return True

    async def search_events(
        self,
        tg_id: int,
        query: str,
        days_ahead: int = 30
    ) -> list[EventModel]:
        user = await self._get_user(tg_id)
        service = await self.credentials_manager.get_service(user.id)

        now = datetime.now(timezone.utc)
        time_max = now + timedelta(days=days_ahead)

        result = await self.credentials_manager._run_sync(
            service.events().list(
                calendarId="primary",
                q=query,
                timeMin=now.isoformat(),
                timeMax=time_max.isoformat(),
                singleEvents=True,
                orderBy="startTime"
            ).execute
        )
        self.logger.info(f"Search '{query}' for tg_id={tg_id}: {len(result.get('items', []))} results")
        return preprocess_event_data(result.get("items", []))

    async def get_events_range(
        self,
        tg_id: int,
        start: datetime,
        end: datetime,
    ) -> list[EventModel]:
        user = await self._get_user(tg_id)
        service = await self.credentials_manager.get_service(user.id)

        result = await self.credentials_manager._run_sync(
            service.events().list(
                calendarId="primary",
                timeMin=start.isoformat(),
                timeMax=end.isoformat(),
                singleEvents=True,
                orderBy="startTime"
            ).execute
        )
        self.logger.info(f"Fetched events range {start.date()}—{end.date()} for tg_id={tg_id}")
        return preprocess_event_data(result.get("items", []))