from loguru import logger
from langchain_openai import ChatOpenAI

from data.init_configs import get_config
from src.agents.llms.base import BaseLLM


class GetOpenAILLM(BaseLLM):
    _llm: ChatOpenAI | None = None
    _initialized = False

    async def get_llm(self) -> ChatOpenAI:
        if not self._initialized:
            config = get_config()
            cfg = config.OPENAI_CONFIG
            base = config.BASE_LLM_CONFIG

            self._llm = ChatOpenAI(
                model=cfg.OPENAI_MODEL,
                max_tokens=base.MAX_TOKENS,
                temperature=base.TEMPERATURE,
                timeout=base.TIMEOUT,
                verbose=base.VERBOSE,
                api_key=cfg.OPENAI_API_KEY,
                model_kwargs={"top_p": base.TOP_P},
            )

            self._initialized = True
            logger.success("✓ GetOpenAILLM инициализирован")

        return self._llm

    def __repr__(self) -> str:
        if not self._initialized or self._llm is None:
            return f"{self.__class__.__name__}(not initialized)"

        return (
            f"{self.__class__.__name__}("
            f"model={self._llm.model_name}, "
            f"max_tokens={self._llm.max_tokens}, "
            f"temperature={self._llm.temperature})"
        )