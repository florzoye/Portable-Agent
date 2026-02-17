from pydantic import BaseModel
from datetime import datetime
from typing import List, Optional

class GoogleOAuthData(BaseModel):
    google_id: Optional[str] = None
    access_token: str
    refresh_token: Optional[str] = None
    token_expiry: Optional[datetime] = None
    token_type: Optional[str] = "Bearer"
    scopes: Optional[List[str]] = None

class GoogleTokenCreate(BaseModel):
    user_id: int
    access_token: str
    refresh_token: Optional[str] = None
    token_expiry: Optional[datetime] = None
    token_type: Optional[str] = "Bearer"
    scopes: Optional[str] = None  

class GoogleTokenResponse(BaseModel):
    id: int
    user_id: int
    access_token: str
    refresh_token: Optional[str] = None
    token_expiry: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True