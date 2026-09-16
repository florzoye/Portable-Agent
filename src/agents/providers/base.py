from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from langchain_core.language_models import BaseChatModel

from src.services.models.providers import ModelProvider, ProviderCapabilities


class ProviderConfigurationError(ValueError):
    """A provider profile cannot be used with its current configuration."""


@dataclass(frozen=True, slots=True)
class ProviderContext:
    user_id: int
    model_name: str
    api_key: str | None


class ProviderAdapter(ABC):
    capabilities: ProviderCapabilities

    @abstractmethod
    async def validate(self, context: ProviderContext) -> None:
        ...

    @abstractmethod
    async def create_model(self, context: ProviderContext) -> BaseChatModel:
        ...

    def validate_configuration(self, context: ProviderContext) -> None:
        if self.capabilities.requires_user_api_key and not context.api_key:
            raise ProviderConfigurationError(
                f"{self.capabilities.display_name} requires an API key"
            )

    def diagnostics(self) -> dict[str, Any]:
        return {
            "provider": self.capabilities.provider.value,
            "display_name": self.capabilities.display_name,
            "developer_managed": self.capabilities.developer_managed,
        }
