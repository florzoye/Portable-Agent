from typing import Optional
from datetime import datetime, date
from pydantic import BaseModel, Field

class CreateEventRequest(BaseModel):
    user_id: str = Field(..., example="123")
    title: str = Field(..., min_length=1, example="Встреча")
    start_time: datetime = Field(..., example="2026-02-20T10:00:00+00:00")
    end_time: datetime = Field(..., example="2026-02-20T11:00:00+00:00")
    description: Optional[str] = Field(None, example="Обсуждение проекта")
    location: Optional[str] = Field(None, example="Zoom")

class EventDateTime(BaseModel):
    day: Optional[date] = Field(None, alias="date")
    time: Optional[datetime] = Field(None, alias="dateTime")
    timezone: Optional[str] = Field(None, alias="timeZone")

    model_config = {"populate_by_name": True}

class EventCreator(BaseModel):
    email: Optional[str] = Field(None, example="user@example.com")
    displayName: Optional[str] = Field(None, example="Иван Иванов")
    self: Optional[bool] = Field(None, example=False)

class EventModel(BaseModel):
    id: str
    status: Optional[str] = None
    summary: Optional[str] = None
    description: Optional[str] = None
    start: Optional[EventDateTime] = None
    end: Optional[EventDateTime] = None
    creator: Optional[EventCreator] = None
    organizer: Optional[EventCreator] = None

class EventsResponse(BaseModel):
    events: list[EventModel]