from typing import Optional
from datetime import datetime, date
from pydantic import BaseModel, Field, field_validator

class CreateEventRequest(BaseModel):
    user_id: str | int  = Field(..., example="123")
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

class UpdateEventRequest(BaseModel):
    user_id: int
    title: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    description: Optional[str] = None
    location: Optional[str] = None
    attendees: Optional[list[str]] = None
    timezone: str = "UTC"

    @field_validator("end_time")
    @classmethod
    def end_after_start(cls, end_time, info):
        if end_time and "start_time" in info.data and info.data["start_time"]:
            if end_time <= info.data["start_time"]:
                raise ValueError("end_time must be after start_time")
        return end_time
    
class EventResponse(BaseModel):
    event: dict

class SearchEventsRequest(BaseModel):
    user_id: int
    query: str
    days_ahead: int = 30


class EventsRangeRequest(BaseModel):
    user_id: int
    start: datetime
    end: datetime

    @field_validator("end")
    @classmethod
    def end_after_start(cls, end, info):
        if "start" in info.data and end <= info.data["start"]:
            raise ValueError("end must be after start")
        return end
