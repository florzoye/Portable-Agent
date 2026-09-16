import unittest

from langchain_core.language_models import BaseChatModel

from src.agents.providers.base import ProviderAdapter, ProviderContext
from src.agents.providers.registry import ProviderRegistry
from src.services.models.providers import ModelProvider
from tests.provider_contract import assert_provider_contract


class _FakeModel(BaseChatModel):
    @property
    def _llm_type(self) -> str:
        return "provider-contract-test"

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        raise NotImplementedError

    async def ainvoke(self, input, config=None, **kwargs):
        return "OK"


class ProviderContractTests(unittest.IsolatedAsyncioTestCase):
    async def test_registered_adapters_follow_shared_contract(self):
        registry = ProviderRegistry()
        for provider in ModelProvider:
            adapter = registry.get(provider)
            self.assertIsInstance(adapter, ProviderAdapter)
            await assert_provider_contract(
                adapter,
                provider,
                api_key=None if provider is ModelProvider.OLLAMA else "test-key",
                model_factory=lambda _context: _fake_model(),
            )


async def _fake_model() -> BaseChatModel:
    return _FakeModel()
