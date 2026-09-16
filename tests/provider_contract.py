from collections.abc import Awaitable, Callable
from typing import Any

from langchain_core.language_models import BaseChatModel

from src.agents.providers.base import (
    ProviderAdapter,
    ProviderConfigurationError,
    ProviderContext,
)
from src.services.models.providers import ModelProvider


async def assert_provider_contract(
    adapter: ProviderAdapter,
    provider: ModelProvider,
    *,
    model_name: str = "test-model",
    api_key: str | None = "test-key",
    model_factory: Callable[[ProviderContext], Awaitable[BaseChatModel]] | None = None,
) -> None:
    """Exercise the provider lifecycle shared by every registered adapter."""
    assert adapter.capabilities.provider is provider
    assert adapter.capabilities.display_name

    context = ProviderContext(
        user_id=1,
        model_name=model_name,
        api_key=api_key,
    )
    await adapter.validate(context)

    if adapter.capabilities.requires_user_api_key:
        try:
            await adapter.validate(
                ProviderContext(user_id=1, model_name=model_name, api_key=None)
            )
        except ProviderConfigurationError:
            pass
        else:
            raise AssertionError("provider accepted a missing user API key")

    assert adapter.diagnostics()["provider"] == provider.value
    assert isinstance(adapter.diagnostics()["display_name"], str)

    if model_factory is not None:
        created: dict[str, Any] = {}

        async def create_model(context: ProviderContext) -> BaseChatModel:
            created["context"] = context
            return await model_factory(context)

        adapter.create_model = create_model  # type: ignore[method-assign]
        await adapter.health_check(context, check_upstream=True)
        assert created["context"] == context
