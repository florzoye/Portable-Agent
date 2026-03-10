import pkgutil
import importlib
from typing import List, Type
from loguru import logger

from src.agents.llms.base import BaseLLM
from langchain_core.language_models import BaseChatModel


class LLMInitializer:
    _initialized: bool = False
    _llm_instances: List[BaseChatModel] = []
    _wrappers: List[BaseLLM] = []

    @classmethod
    def _load_modules(cls, path: str = "src/agents/llms"):
        logger.info("Loading LLM modules...")

        for _, module_name, _ in pkgutil.iter_modules([path]):
            if module_name.startswith("_") or module_name in ("base", "initializer"):
                continue

            try:
                importlib.import_module(f"src.agents.llms.{module_name}")
                logger.success(f"✓ LLM module loaded: {module_name}")
            except Exception as e:
                logger.warning(f"⚠ Failed to load {module_name}: {e}")

    @classmethod
    def _get_llm_classes(cls) -> List[Type[BaseLLM]]:
        return BaseLLM.__subclasses__()

    @classmethod
    async def initialize(cls) -> List[BaseChatModel]:
        if cls._initialized:
            logger.warning("⚠ LLM is already initialized")
            return cls._llm_instances

        cls._load_modules()

        llm_classes = cls._get_llm_classes()
        if not llm_classes:
            raise RuntimeError("❌ No registered LLM classes")

        logger.info(f"Найдено LLM классов: {[c.__name__ for c in llm_classes]}")

        for llm_class in llm_classes:
            try:
                wrapper = llm_class()  # singleton
                llm = await wrapper.get_llm()

                cls._wrappers.append(wrapper)
                cls._llm_instances.append(llm)

                logger.success(f"✓ {llm_class.__name__} initialized")
            except Exception as e:
                logger.error(f"✗Initialization error {llm_class.__name__}: {e}")

        if not cls._llm_instances:
            raise RuntimeError("❌Failed to initialize any LLMs")

        cls._initialized = True
        logger.success(f"🎉LLM initialized: {len(cls._llm_instances)}")

        return cls._llm_instances

    @classmethod
    def get_llms(cls) -> List[BaseChatModel]:
        if not cls._initialized:
            raise RuntimeError("LLM is not initialized")
        return cls._llm_instances

    @classmethod
    def get_wrappers(cls) -> List[BaseLLM]:
        if not cls._initialized:
            raise RuntimeError("LLM is not initialized")
        return cls._wrappers