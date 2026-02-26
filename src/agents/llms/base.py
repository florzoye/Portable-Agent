from typing import Any
from abc import ABC, abstractmethod
from langchain_core.language_models import BaseChatModel

class BaseLLM(ABC):
    _instance = None
    _response_format: Any = None 

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @abstractmethod
    async def get_llm(self) -> BaseChatModel:
        ...