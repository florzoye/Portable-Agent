from loguru import logger
from langchain_ollama import ChatOllama

from data.init_configs import get_config
from src.agents.llms.base import BaseLLM


class GetOllamaLLM(BaseLLM):
    _llm: ChatOllama | None = None
    _initialized = False

    async def get_llm(self) -> ChatOllama:
        if not self._initialized:
            config = get_config()
            cfg = config.OLLAMA_CONFIG
            base = config.BASE_LLM_CONFIG

            self._llm = ChatOllama(
                model=cfg.OLLAMA_MODEL,
                num_predict=base.MAX_TOKENS, 
                temperature=base.TEMPERATURE,
                timeout=base.TIMEOUT,
                top_p=base.TOP_P,
                verbose=base.VERBOSE,
                base_url=cfg.OLLAMA_HOST,
            )

            self._initialized = True
            logger.success("✓ GetOllamaLLM инициализирован")

        return self._llm

    def __repr__(self) -> str:
        if not self._initialized or self._llm is None:
            return f"{self.__class__.__name__}(not initialized)"

        return (
            f"{self.__class__.__name__}("
            f"model={self._llm.model}, "
            f"num_predict={self._llm.num_predict}, "
            f"temperature={self._llm.temperature})"
        )