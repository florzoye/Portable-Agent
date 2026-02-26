from loguru import logger
from langchain_ollama import ChatOllama

from data.init_configs import get_config
from src.agents.llms.base import BaseLLM


class GetOllamaLLM(BaseLLM):
    _llm = None
    _initialized = False

    async def get_llm(self):
        if not self._initialized:
            config = get_config()

            self._llm = ChatOllama(
                model=config.OLLAMA_CONFIG.OLLAMA_MODEL,
                max_tokens=config.BASE_LLM_CONFIG.MAX_TOKENS,
                temperature=config.BASE_LLM_CONFIG.TEMPERATURE,
                timeout=config.BASE_LLM_CONFIG.TIMEOUT,
                top_p=config.BASE_LLM_CONFIG.TOP_P,
                verbose=config.BASE_LLM_CONFIG.VERBOSE,
                base_url=config.OLLAMA_CONFIG.OLLAMA_HOST
            )

            self._initialized = True
            logger.success("✓ GetOllamaLLM инициализирован")

        return self._llm
               
    def __repr__(self) -> str:
        if not self._initialized:
            return f"{self.__class__.__name__}(not initialized)"
        
        return (
            f"{self.__class__.__name__}("
            f"model={self._ollama_config.OLLAMA_MODEL}, "
            f"max_tokens={self._base_llm_config.MAX_TOKENS}, "
            f"temperature={self._base_llm_config.TEMPERATURE}, "
            f"timeout={self._base_llm_config.TIMEOUT})"
        )