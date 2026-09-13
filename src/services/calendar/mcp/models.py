from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field, field_validator


class CreateEventParams(BaseModel):
    user_id: int
    title: str = Field(..., min_length=1, max_length=200)
    start_time: datetime
    end_time: datetime
    description: Optional[str] = None
    location: Optional[str] = None
    attendees: Optional[list[str]] = None
    timezone: str = Field("UTC", min_length=1, max_length=64)

    @field_validator("end_time")
    @classmethod
    def end_after_start(cls, end_time, info):
        if "start_time" in info.data and end_time <= info.data["start_time"]:
            raise ValueError("the end time is less than the start time")
        return end_time


class UpdateEventParams(BaseModel):
    user_id: int
    title: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    description: Optional[str] = None
    location: Optional[str] = None
    timezone: str = Field("UTC", min_length=1, max_length=64)


class EventsRangeParams(BaseModel):
    user_id: int
    start: datetime
    end: datetime

    @field_validator("start", "end")
    @classmethod
    def require_timezone(cls, value):
        if value.tzinfo is None:
            raise ValueError("datetime must include a timezone")
        return value

    @field_validator("end")
    @classmethod
    def end_after_start(cls, end, info):
        if "start" in info.data and end <= info.data["start"]:
            raise ValueError("the end time is less than the start time")
        return end