from typing import Optional
from datetime import datetime
from pydantic import BaseModel

class TokenModel(BaseModel):
    id: Optional[int] = None
    user_id: int
    access_token: str
    refresh_token: Optional[str] = None

    token_type: str = "Bearer"
    scopes: Optional[str] = None           

    token_expiry: Optional[datetime] = None  
    created_at: Optional[datetime] = None    
    updated_at: Optional[datetime] = None    

    class Config:
        from_attributes = True