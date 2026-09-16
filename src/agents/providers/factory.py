from langchain_core.language_models import BaseChatModel

from db.model_profiles_protocol import ModelProfilesBase
from src.agents.providers.base import ProviderContext
from src.agents.providers.registry import ProviderRegistry
from src.services.models.providers import ModelProvider


class UserModelFactory:
    def __init__(
        self,
        profiles: ModelProfilesBase,
        registry: ProviderRegistry | None = None,
    ):
        self.profiles = profiles
        self.registry = registry or ProviderRegistry()

    async def create_for_profile(
        self,
        user_id: int,
        profile_id: int,
    ) -> BaseChatModel:
        profile = next(
            (
                profile
                for profile in await self.profiles.list_for_user(user_id)
                if profile.id == profile_id
            ),
            None,
        )
        if profile is None:
            raise ValueError("Model profile not found")
        api_key = await self.profiles.get_api_key(user_id, profile_id)
        adapter = self.registry.get(profile.provider)
        context = ProviderContext(user_id, profile.model_name, api_key)
        await adapter.validate(context)
        return await adapter.create_model(context)

    async def create_active(self, user_id: int) -> BaseChatModel | None:
        profile = await self.profiles.get_active(user_id)
        if profile is None:
            return None
        return await self.create_for_profile(user_id, profile.id)

    async def create_developer_ollama(
        self,
        user_id: int,
        model_name: str,
    ) -> BaseChatModel:
        adapter = self.registry.get(ModelProvider.OLLAMA)
        context = ProviderContext(user_id, model_name, None)
        await adapter.validate(context)
        return await adapter.create_model(context)
