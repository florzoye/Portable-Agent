from collections.abc import Sequence

from db.model_profiles_protocol import ModelProfilesBase
from db.database import Database
from src.agents.providers.base import ProviderConfigurationError
from src.agents.providers.registry import ProviderRegistry
from src.services.models.providers import (
    ModelProvider,
    ProviderCapabilities,
    UserModelProfile,
)


class ModelProfileService:
    def __init__(
        self,
        profiles: ModelProfilesBase,
        registry: ProviderRegistry | None = None,
    ):
        self.profiles = profiles
        self.registry = registry or ProviderRegistry()

    def available_providers(self) -> tuple[ProviderCapabilities, ...]:
        return self.registry.capabilities()

    async def list(self, user_id: int) -> Sequence[UserModelProfile]:
        return await self.profiles.list_for_user(user_id)

    async def add(
        self,
        user_id: int,
        provider: ModelProvider,
        model_name: str,
        display_name: str,
        api_key: str | None = None,
    ) -> UserModelProfile:
        adapter = self.registry.get(provider)
        if adapter.capabilities.developer_managed:
            api_key = None
        elif not api_key or not api_key.strip():
            raise ProviderConfigurationError(
                f"{adapter.capabilities.display_name} requires your API key"
            )
        elif api_key is not None:
            api_key = api_key.strip()
        model_name = model_name.strip()
        display_name = display_name.strip() or model_name
        if not model_name:
            raise ValueError("Model name is required")
        return await self.profiles.create(
            user_id,
            provider,
            model_name,
            display_name,
            api_key,
        )

    async def activate(self, user_id: int, profile_id: int) -> UserModelProfile:
        return await self.profiles.activate(user_id, profile_id)

    async def delete(self, user_id: int, profile_id: int) -> bool:
        return await self.profiles.delete(user_id, profile_id)


class ModelProfileApplication:
    """Transaction-owning application facade shared by transport adapters."""

    def __init__(self, database: Database):
        self.database = database

    async def list(self, user_id: int) -> Sequence[UserModelProfile]:
        async with self.database.transaction() as session:
            return await ModelProfileService(
                self.database.get_model_profiles_repo(session)
            ).list(user_id)

    async def add(
        self,
        user_id: int,
        provider: ModelProvider,
        model_name: str,
        display_name: str,
        api_key: str | None = None,
    ) -> UserModelProfile:
        async with self.database.transaction() as session:
            return await ModelProfileService(
                self.database.get_model_profiles_repo(session)
            ).add(user_id, provider, model_name, display_name, api_key)

    async def activate(self, user_id: int, profile_id: int) -> UserModelProfile:
        async with self.database.transaction() as session:
            return await ModelProfileService(
                self.database.get_model_profiles_repo(session)
            ).activate(user_id, profile_id)

    async def delete(self, user_id: int, profile_id: int) -> bool:
        async with self.database.transaction() as session:
            return await ModelProfileService(
                self.database.get_model_profiles_repo(session)
            ).delete(user_id, profile_id)
