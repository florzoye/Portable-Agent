from loguru import logger
from langchain_xai import ChatXAI

from data.init_configs import get_config
from src.agents.llms.base import BaseLLM


class GetXaiLLM(BaseLLM):
    _llm: ChatXAI | None = None
    _initialized = False

    async def get_llm(self) -> ChatXAI:
        if not self._initialized:
            config = get_config()
            cfg = config.XAI_CONFIG
            base = config.BASE_LLM_CONFIG

            self._llm = ChatXAI(
                model=cfg.XAI_MODEL,
                temperature=base.TEMPERATURE,
                top_p=base.TOP_P,
                verbose=base.VERBOSE,
                api_key=cfg.XAI_API_KEY,
                streaming=True
            )

            self._initialized = True
            logger.success("✓ GetXaiLLM initialized")

        return self._llm

    def __repr__(self) -> str:
        if not self._initialized or self._llm is None:
            return f"{self.__class__.__name__}(not initialized)"

        return (
            f"{self.__class__.__name__}("
            f"model={self._llm.model}, "
            f"temperature={self._llm.temperature}, "
            f"streaming={self._llm.streaming}"
        )