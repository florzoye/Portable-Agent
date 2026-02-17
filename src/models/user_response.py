from typing import Optional
from pydantic import BaseModel

class UserCreate(BaseModel):
    tg_id: int
    tg_nick: Optional[str] = None
    email: Optional[str] = None
    google_id: Optional[str] = None

class UserResponse(BaseModel):
    id: int
    tg_id: int
    tg_nick: Optional[str] = None
    email: Optional[str] = None
    google_id: Optional[str] = None
    has_google_token: bool = False

    class Config:
        from_attributes = True