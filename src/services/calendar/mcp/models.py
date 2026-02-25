from typing import Optional
from datetime import datetime
from pydantic import BaseModel, field_validator


class CreateEventParams(BaseModel):
    user_id: int
    title: str
    start_time: datetime
    end_time: datetime
    description: Optional[str] = None
    location: Optional[str] = None
    attendees: Optional[list[str]] = None
    timezone: str = "UTC"

    @field_validator("end_time")
    @classmethod
    def end_after_start(cls, end_time, info):
        if "start_time" in info.data and end_time <= info.data["start_time"]:
            raise ValueError("конечное время меньше начального")
        return end_time


class UpdateEventParams(BaseModel):
    user_id: int
    title: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    description: Optional[str] = None
    location: Optional[str] = None
    timezone: str = "UTC"


class EventsRangeParams(BaseModel):
    user_id: int
    start: datetime
    end: datetime

    @field_validator("end")
    @classmethod
    def end_after_start(cls, end, info):
        if "start" in info.data and end <= info.data["start"]:
            raise ValueError("конечное время меньше начального")
        return end