from src.agents.providers.adapters import OllamaProvider, OpenAIProvider, XAIProvider
from src.agents.providers.base import ProviderAdapter
from src.services.models.providers import ModelProvider


class ProviderRegistry:
    def __init__(self):
        self._providers: dict[ModelProvider, ProviderAdapter] = {
            ModelProvider.OPENAI: OpenAIProvider(),
            ModelProvider.XAI: XAIProvider(),
            ModelProvider.OLLAMA: OllamaProvider(),
        }

    def get(self, provider: ModelProvider) -> ProviderAdapter:
        try:
            return self._providers[provider]
        except KeyError as exc:
            raise ValueError(f"Unsupported model provider: {provider}") from exc

    def capabilities(self):
        return tuple(adapter.capabilities for adapter in self._providers.values())
