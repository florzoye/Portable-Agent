from typing import Optional
from datetime import datetime
from pydantic import BaseModel

class UserModel(BaseModel):
    id: Optional[int] = None
    tg_id: int
    tg_nick: Optional[str] = None
    email: Optional[str] = None
    google_id: Optional[str] = None
    created_at: datetime = None
    updated_at: datetime = None

    class Config:
        from_attributes = True