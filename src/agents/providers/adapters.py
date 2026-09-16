from langchain_ollama import ChatOllama
from langchain_openai import ChatOpenAI
from langchain_xai import ChatXAI

from data import get_config
from src.agents.providers.base import ProviderAdapter, ProviderContext
from src.services.models.providers import ModelProvider, ProviderCapabilities


class OpenAIProvider(ProviderAdapter):
    capabilities = ProviderCapabilities(ModelProvider.OPENAI, "OpenAI", True)

    async def validate(self, context: ProviderContext) -> None:
        self.validate_configuration(context)

    async def create_model(self, context: ProviderContext) -> ChatOpenAI:
        self.validate_configuration(context)
        base = get_config().BASE_LLM_CONFIG
        return ChatOpenAI(
            model=context.model_name,
            max_tokens=base.MAX_TOKENS,
            temperature=base.TEMPERATURE,
            timeout=base.TIMEOUT,
            verbose=base.VERBOSE,
            api_key=context.api_key,
            model_kwargs={"top_p": base.TOP_P},
        )


class XAIProvider(ProviderAdapter):
    capabilities = ProviderCapabilities(ModelProvider.XAI, "xAI", True)

    async def validate(self, context: ProviderContext) -> None:
        self.validate_configuration(context)

    async def create_model(self, context: ProviderContext) -> ChatXAI:
        self.validate_configuration(context)
        base = get_config().BASE_LLM_CONFIG
        return ChatXAI(
            model=context.model_name,
            temperature=base.TEMPERATURE,
            top_p=base.TOP_P,
            verbose=base.VERBOSE,
            api_key=context.api_key,
            streaming=True,
        )


class OllamaProvider(ProviderAdapter):
    capabilities = ProviderCapabilities(
        ModelProvider.OLLAMA,
        "Ollama (developer hosted)",
        False,
        developer_managed=True,
    )

    async def validate(self, context: ProviderContext) -> None:
        self.validate_configuration(context)

    async def create_model(self, context: ProviderContext) -> ChatOllama:
        self.validate_configuration(context)
        base = get_config().BASE_LLM_CONFIG
        cfg = get_config().OLLAMA_CONFIG
        return ChatOllama(
            model=context.model_name,
            num_predict=base.MAX_TOKENS,
            temperature=base.TEMPERATURE,
            timeout=base.TIMEOUT,
            top_p=base.TOP_P,
            verbose=base.VERBOSE,
            base_url=cfg.OLLAMA_HOST,
        )
