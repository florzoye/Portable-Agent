from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from langchain_core.language_models import BaseChatModel

from src.services.models.providers import ModelProvider, ProviderCapabilities


class ProviderError(RuntimeError):
    """Base class for safe provider failures exposed to application layers."""


class ProviderConfigurationError(ProviderError, ValueError):
    """A provider profile cannot be used with its current configuration."""


class ProviderUnavailableError(ProviderError):
    """The configured provider cannot currently be reached."""


class ProviderTimeoutError(ProviderUnavailableError):
    """The provider did not respond within the configured timeout."""


class ProviderRequestError(ProviderError):
    """The provider rejected a request without exposing its raw response."""


def provider_user_message(error: BaseException) -> str:
    if isinstance(error, ProviderConfigurationError):
        return "Проверьте настройки модели и API-ключ."
    if isinstance(error, ProviderTimeoutError):
        return "Провайдер не ответил вовремя. Попробуйте ещё раз."
    if isinstance(error, ProviderUnavailableError):
        return "Провайдер временно недоступен. Попробуйте позже."
    if isinstance(error, ProviderRequestError):
        return "Провайдер отклонил запрос. Проверьте модель и доступ к ней."
    return "Произошла ошибка. Попробуйте ещё раз."


def normalize_provider_error(error: Exception) -> ProviderError:
    error_name = type(error).__name__.lower()
    if isinstance(error, TimeoutError) or "timeout" in error_name:
        return ProviderTimeoutError("Provider request timed out")
    if isinstance(error, (OSError, ConnectionError)) or any(
        marker in error_name for marker in ("connection", "network", "unavailable")
    ):
        return ProviderUnavailableError("Provider is unavailable")
    return ProviderRequestError("Provider rejected the request")


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
