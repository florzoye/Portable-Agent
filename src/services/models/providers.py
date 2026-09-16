from dataclasses import dataclass
from enum import StrEnum


class ModelProvider(StrEnum):
    OPENAI = "openai"
    XAI = "xai"
    OLLAMA = "ollama"


@dataclass(frozen=True, slots=True)
class ProviderCapabilities:
    provider: ModelProvider
    display_name: str
    requires_user_api_key: bool
    developer_managed: bool = False


@dataclass(frozen=True, slots=True)
class UserModelProfile:
    id: int
    user_id: int
    provider: ModelProvider
    model_name: str
    display_name: str
    is_active: bool


@dataclass(frozen=True, slots=True)
class DeveloperModelProfile:
    provider: ModelProvider
    model_name: str
    display_name: str
