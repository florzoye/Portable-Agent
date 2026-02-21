import aiohttp
from typing import Any, Optional
from utils.const import GOOGLE_CALENDAR_URI

class AsyncHTTPClient:
    def __init__(self, base_url: str = GOOGLE_CALENDAR_URI, timeout: int = 30):
        self.base_url = base_url.rstrip("/") + "/"
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self._session: Optional[aiohttp.ClientSession] = None

    async def __aenter__(self) -> "AsyncHTTPClient":
        self._session = aiohttp.ClientSession(
            base_url=self.base_url,
            timeout=self.timeout
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        if self._session:
            await self._session.close()
            self._session = None

    def _get_session(self) -> aiohttp.ClientSession:
        if not self._session:
            raise RuntimeError
        return self._session

    async def get(self, path: str, params: Optional[dict] = None) -> tuple[int, Any]:
        async with self._get_session().get(path, params=params) as r:
            return r.status, await r.json()

    async def post(self, path: str, json: Optional[dict] = None) -> tuple[int, Any]:
        async with self._get_session().post(path, json=json) as r:
            return r.status, await r.json()

    async def patch(self, path: str, json: Optional[dict] = None) -> tuple[int, Any]:
        async with self._get_session().patch(path, json=json) as r:
            return r.status, await r.json()

    async def delete(self, path: str, params: Optional[dict] = None) -> tuple[int, Any]:
        async with self._get_session().delete(path, params=params) as r:
            return r.status, await r.json()