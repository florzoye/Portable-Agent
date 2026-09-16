from collections.abc import Sequence

from db.model_profiles_protocol import ModelProfilesBase
from db.database import Database
from db.database_protocol import UsersBase
from data import get_config
from src.agents.providers.factory import UserModelFactory
from data.configs.tenant_config import TenantLimitsConfig
from src.agents.providers.base import (
    ProviderConfigurationError,
    ProviderError,
    ProviderContext,
    provider_user_message,
)
from src.agents.providers.registry import ProviderRegistry
from src.services.models.providers import (
    ModelProvider,
    ProviderCapabilities,
    UserModelProfile,
)
from utils.observability import emit_event


def _audit_profile_event(
    action: str,
    user_id: int,
    *,
    result: str,
    profile_id: int | None = None,
    provider: ModelProvider | None = None,
    error_category: str | None = None,
    diagnostic_mode: str | None = None,
) -> None:
    fields = {
        "user_id": user_id,
        "action": action,
        "result": result,
    }
    if profile_id is not None:
        fields["profile_id"] = profile_id
    if provider is not None:
        fields["provider"] = provider.value
    if error_category is not None:
        fields["error_category"] = error_category
    if diagnostic_mode is not None:
        fields["diagnostic_mode"] = diagnostic_mode
    emit_event("model_profile.audit", **fields)


def _error_category(error: BaseException) -> str:
    if isinstance(error, ProviderConfigurationError):
        return "configuration"
    if isinstance(error, ProviderError):
        return "provider"
    if isinstance(error, ValueError):
        return "validation"
    return "internal"


class ModelProfileService:
    def __init__(
        self,
        profiles: ModelProfilesBase,
        registry: ProviderRegistry | None = None,
        limits: TenantLimitsConfig | None = None,
    ):
        self.profiles = profiles
        self.registry = registry or ProviderRegistry()
        if limits is None:
            raise ValueError("Tenant limits configuration is required")
        self.limits = limits

    def available_providers(self) -> tuple[ProviderCapabilities, ...]:
        return self.registry.capabilities()

    async def list(self, user_id: int) -> Sequence[UserModelProfile]:
        return await self.profiles.list_for_user(user_id)

    async def create_active_model(self, user_id: int):
        factory = UserModelFactory(self.profiles, self.registry)
        return await factory.create_active(user_id)

    async def diagnose(
        self,
        user_id: int,
        profile_id: int,
        check_upstream: bool = False,
    ):
        from src.services.models.providers import ProviderDiagnostic

        profile = next(
            (
                item
                for item in await self.profiles.list_for_user(user_id)
                if item.id == profile_id
            ),
            None,
        )
        if profile is None:
            _audit_profile_event(
                "diagnose",
                user_id,
                result="not_found",
                profile_id=profile_id,
            )
            raise ValueError("Model profile not found")
        diagnostic_mode = "upstream" if check_upstream else "local"
        try:
            api_key = await self.profiles.get_api_key(user_id, profile_id)
            adapter = self.registry.get(profile.provider)
            context = ProviderContext(user_id, profile.model_name, api_key)
            await adapter.health_check(context, check_upstream)
        except Exception as error:
            _audit_profile_event(
                "diagnose",
                user_id,
                result="failed",
                profile_id=profile.id,
                provider=profile.provider,
                error_category=_error_category(error),
                diagnostic_mode=diagnostic_mode,
            )
            if not isinstance(error, ProviderError):
                raise
            return ProviderDiagnostic(
                profile.id,
                profile.provider,
                profile.model_name,
                "unhealthy",
                provider_user_message(error),
                check_upstream,
            )
        _audit_profile_event(
            "diagnose",
            user_id,
            result="healthy",
            profile_id=profile.id,
            provider=profile.provider,
            diagnostic_mode=diagnostic_mode,
        )
        return ProviderDiagnostic(
            profile.id,
            profile.provider,
            profile.model_name,
            "healthy",
            "Конфигурация корректна"
            if not check_upstream
            else "Провайдер отвечает",
            check_upstream,
        )

    async def add(
        self,
        user_id: int,
        provider: ModelProvider,
        model_name: str,
        display_name: str,
        api_key: str | None = None,
    ) -> UserModelProfile:
        try:
            if len(await self.profiles.list_for_user(user_id)) >= self.limits.MAX_MODEL_PROFILES:
                raise ValueError("Model profile limit reached")
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
            if len(model_name) > self.limits.MAX_MODEL_NAME_LENGTH:
                raise ValueError("Model name is too long")
            if len(display_name) > self.limits.MAX_DISPLAY_NAME_LENGTH:
                raise ValueError("Display name is too long")
            profile = await self.profiles.create(
                user_id,
                provider,
                model_name,
                display_name,
                api_key,
            )
        except Exception as error:
            _audit_profile_event(
                "create",
                user_id,
                result="failed",
                provider=provider,
                error_category=_error_category(error),
            )
            raise
        _audit_profile_event(
            "create",
            user_id,
            result="succeeded",
            profile_id=profile.id,
            provider=profile.provider,
        )
        return profile

    async def activate(self, user_id: int, profile_id: int) -> UserModelProfile:
        try:
            profile = await self.profiles.activate(user_id, profile_id)
        except Exception as error:
            _audit_profile_event(
                "activate",
                user_id,
                result="failed",
                profile_id=profile_id,
                error_category=_error_category(error),
            )
            raise
        UserModelFactory.invalidate_user(user_id)
        _audit_profile_event(
            "activate",
            user_id,
            result="succeeded",
            profile_id=profile.id,
            provider=profile.provider,
        )
        return profile

    async def delete(self, user_id: int, profile_id: int) -> bool:
        try:
            deleted = await self.profiles.delete(user_id, profile_id)
        except Exception as error:
            _audit_profile_event(
                "delete",
                user_id,
                result="failed",
                profile_id=profile_id,
                error_category=_error_category(error),
            )
            raise
        if deleted:
            UserModelFactory.invalidate_user(user_id)
            _audit_profile_event(
                "delete",
                user_id,
                result="succeeded",
                profile_id=profile_id,
            )
        else:
            _audit_profile_event(
                "delete",
                user_id,
                result="not_found",
                profile_id=profile_id,
            )
        return deleted


class ModelProfileApplication:
    """Transaction-owning application facade shared by transport adapters."""

    def __init__(
        self,
        database: Database,
        registry: ProviderRegistry | None = None,
    ):
        self.database = database
        self.registry = registry or ProviderRegistry()

    def _service(self, session) -> ModelProfileService:
        return ModelProfileService(
            self.database.get_model_profiles_repo(session),
            registry=self.registry,
            limits=get_config().TENANT_LIMITS,
        )

    def available_providers(self) -> tuple[ProviderCapabilities, ...]:
        return self.registry.capabilities()

    async def _ensure_user(self, session, tg_id: int) -> None:
        users: UsersBase = self.database.get_users_repo(session)
        if await users.get_user_by_tg_id(tg_id) is not None:
            return
        if await users.add_user(tg_id) is None:
            raise RuntimeError(f"Unable to initialize tenant {tg_id}")

    async def list(self, user_id: int) -> Sequence[UserModelProfile]:
        async with self.database.transaction() as session:
            return await self._service(session).list(user_id)

    async def create_active_model(self, user_id: int):
        async with self.database.transaction() as session:
            return await self._service(session).create_active_model(user_id)

    async def diagnose(
        self,
        user_id: int,
        profile_id: int,
        check_upstream: bool = False,
    ):
        async with self.database.transaction() as session:
            return await self._service(session).diagnose(
                user_id, profile_id, check_upstream
            )

    async def add(
        self,
        user_id: int,
        provider: ModelProvider,
        model_name: str,
        display_name: str,
        api_key: str | None = None,
    ) -> UserModelProfile:
        async with self.database.transaction() as session:
            await self._ensure_user(session, user_id)
            return await self._service(session).add(
                user_id, provider, model_name, display_name, api_key
            )

    async def activate(self, user_id: int, profile_id: int) -> UserModelProfile:
        async with self.database.transaction() as session:
            return await self._service(session).activate(user_id, profile_id)

    async def delete(self, user_id: int, profile_id: int) -> bool:
        async with self.database.transaction() as session:
            return await self._service(session).delete(user_id, profile_id)
