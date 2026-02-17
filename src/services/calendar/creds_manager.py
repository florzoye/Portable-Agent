import json
import asyncio
from typing import Any
from concurrent.futures import ThreadPoolExecutor

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

from src.services.calendar.token_service import TokenService

from utils.const import SCOPES
from utils.helpers import DataCreator, DateTimeNormalizer

class CredentialsManager:
    def __init__(self, client_id: str, client_secret: str, token_service: TokenService):
        self.client_id = client_id
        self.client_secret = client_secret
        self.token_service = token_service
        self.executor = ThreadPoolExecutor(max_workers=3)
    
    def _prepare_credentials_dict(self, token_data: Any) -> dict:
        expiry = DateTimeNormalizer.normalize_expiry_from_db(token_data.token_expiry)
        
        credentials_dict = DataCreator.credentials_dict(
            token_data,
            self.client_id,
            self.client_secret
        )
        
        credentials_dict.update({
            "scopes": json.loads(token_data.scopes) if token_data.scopes else SCOPES,
            "expiry": expiry.strftime("%Y-%m-%dT%H:%M:%S.%fZ") if expiry else None
        })
        
        return credentials_dict

    async def _run_sync(self, func, *args, **kwargs):
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self.executor, lambda: func(*args, **kwargs))

    def build_credentials(self, token_data: Any) -> Credentials:
        credentials_dict = self._prepare_credentials_dict(token_data)
        return Credentials.from_authorized_user_info(credentials_dict, SCOPES)

    async def get_service(self, user_id: int):
        token_data = await self.token_service.get_token(user_id)
        if not token_data:
            raise ValueError("Credentials отсутствуют")

        credentials = self.build_credentials(token_data)

        if credentials.expired and credentials.refresh_token:
            await self._run_sync(credentials.refresh, Request())
            await self.token_service.update_token(
                user_id=user_id,
                access_token=credentials.token,
                refresh_token=credentials.refresh_token,
                expiry=credentials.expiry,
            )
            token_data = await self.token_service.get_token(user_id)
            credentials = self.build_credentials(token_data)

        return await self._run_sync(build, "calendar", "v3", credentials=credentials)

    async def load_credentials(self, user_id: int) -> bool:
        token_data = await self.token_service.get_token(user_id)
        if not token_data:
            return False

        credentials = self.build_credentials(token_data)

        if credentials.expired and credentials.refresh_token:
            await self._run_sync(credentials.refresh, Request())
            await self.token_service.update_token(
                user_id=user_id,
                access_token=credentials.token,
                refresh_token=credentials.refresh_token,
                expiry=credentials.expiry,
            )

        return True