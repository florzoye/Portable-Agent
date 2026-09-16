from abc import ABC, abstractmethod
from typing import Sequence

from src.services.models.providers import ModelProvider, UserModelProfile


class ModelProfilesBase(ABC):
    @abstractmethod
    async def list_for_user(self, user_id: int) -> Sequence[UserModelProfile]:
        ...

    @abstractmethod
    async def create(
        self,
        user_id: int,
        provider: ModelProvider,
        model_name: str,
        display_name: str,
        encrypted_api_key: str | None,
    ) -> UserModelProfile:
        ...

    @abstractmethod
    async def get_active(self, user_id: int) -> UserModelProfile | None:
        ...

    @abstractmethod
    async def activate(self, user_id: int, profile_id: int) -> UserModelProfile:
        ...

    @abstractmethod
    async def delete(self, user_id: int, profile_id: int) -> bool:
        ...

    @abstractmethod
    async def get_api_key(self, user_id: int, profile_id: int) -> str | None:
        ...
