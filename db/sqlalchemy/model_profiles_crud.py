from collections.abc import Sequence

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from db.model_profiles_protocol import ModelProfilesBase
from db.sqlalchemy.models import ModelProfile
from src.services.models.providers import ModelProvider, UserModelProfile
from utils.crypto import TokenCipher


class ModelProfilesORM(ModelProfilesBase):
    def __init__(self, session: AsyncSession):
        self.session = session
        self.cipher = TokenCipher()

    @staticmethod
    def _to_model(profile: ModelProfile) -> UserModelProfile:
        return UserModelProfile(
            id=profile.id,
            user_id=profile.user_id,
            provider=ModelProvider(profile.provider),
            model_name=profile.model_name,
            display_name=profile.display_name,
            is_active=profile.is_active,
        )

    async def list_for_user(self, user_id: int) -> Sequence[UserModelProfile]:
        result = await self.session.scalars(
            select(ModelProfile)
            .where(ModelProfile.user_id == user_id)
            .order_by(ModelProfile.created_at, ModelProfile.id)
        )
        return [self._to_model(profile) for profile in result]

    async def create(
        self,
        user_id: int,
        provider: ModelProvider,
        model_name: str,
        display_name: str,
        api_key: str | None,
    ) -> UserModelProfile:
        profile = ModelProfile(
            user_id=user_id,
            provider=provider.value,
            model_name=model_name,
            display_name=display_name,
            encrypted_api_key=(
                self.cipher.encrypt(api_key)
                if api_key is not None
                else None
            ),
            is_active=False,
        )
        self.session.add(profile)
        await self.session.flush()
        return self._to_model(profile)

    async def get_active(self, user_id: int) -> UserModelProfile | None:
        profile = await self.session.scalar(
            select(ModelProfile)
            .where(
                ModelProfile.user_id == user_id,
                ModelProfile.is_active.is_(True),
            )
            .limit(1)
        )
        return self._to_model(profile) if profile else None

    async def activate(self, user_id: int, profile_id: int) -> UserModelProfile:
        profile = await self.session.scalar(
            select(ModelProfile).where(
                ModelProfile.id == profile_id,
                ModelProfile.user_id == user_id,
            )
        )
        if profile is None:
            raise ValueError("Model profile not found")
        await self.session.execute(
            update(ModelProfile)
            .where(ModelProfile.user_id == user_id)
            .values(is_active=False)
        )
        profile.is_active = True
        await self.session.flush()
        return self._to_model(profile)

    async def deactivate(self, user_id: int) -> bool:
        result = await self.session.execute(
            update(ModelProfile)
            .where(
                ModelProfile.user_id == user_id,
                ModelProfile.is_active.is_(True),
            )
            .values(is_active=False)
        )
        await self.session.flush()
        return result.rowcount > 0

    async def delete(self, user_id: int, profile_id: int) -> bool:
        result = await self.session.execute(
            delete(ModelProfile).where(
                ModelProfile.id == profile_id,
                ModelProfile.user_id == user_id,
            )
        )
        return result.rowcount > 0

    async def get_api_key(self, user_id: int, profile_id: int) -> str | None:
        encrypted = await self.session.scalar(
            select(ModelProfile.encrypted_api_key).where(
                ModelProfile.id == profile_id,
                ModelProfile.user_id == user_id,
            )
        )
        return self.cipher.decrypt(encrypted) if encrypted else None
