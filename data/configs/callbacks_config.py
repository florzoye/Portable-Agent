import os
from typing import Optional, List
from .base_config import BaseConfig

from langfuse import Langfuse, get_client
from langfuse.langchain import CallbackHandler
from langchain_core.callbacks.base import BaseCallbackHandler


class LangFuseConfig(BaseConfig):
    USE_LANGFUSE: bool = True
    LANGFUSE_BASE_URL: str
    LANGFUSE_PUBLIC_KEY: str
    LANGFUSE_SECRET_KEY: str


class LangSmithConfig(BaseConfig):
    LANGCHAIN_TRACING_V2: bool = False
    LANGCHAIN_API_KEY: Optional[str] = None
    LANGCHAIN_PROJECT: Optional[str] = None
    LANGCHAIN_ENDPOINT: str = "https://api.smith.langchain.com"


class GlobalCallbacksService:
    _instance = None
    _initialized = False

    def __new__(cls):
        if not cls._instance:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self.langfuse_config: Optional[LangFuseConfig] = None
        self.langsmith_config: Optional[LangSmithConfig] = None
        self.callbacks: List[BaseCallbackHandler] = []
        self.langfuse_handler: Optional[CallbackHandler] = None
        self.client: Optional[Langfuse] = None

    def initialize(self):
        if self._initialized:
            return

        self.langfuse_config = LangFuseConfig()
        self.langsmith_config = LangSmithConfig()
        
        self._init_langsmith()
        self._init_langfuse()

        self._initialized = True

    def _init_langsmith(self) -> None:
        """Инициализация LangSmith трейсинга"""
        if not self.langsmith_config.LANGCHAIN_TRACING_V2:
            return

        os.environ["LANGCHAIN_TRACING_V2"] = "true"
        os.environ["LANGCHAIN_API_KEY"] = self.langsmith_config.LANGCHAIN_API_KEY or ""
        os.environ["LANGCHAIN_PROJECT"] = self.langsmith_config.LANGCHAIN_PROJECT or ""
        os.environ["LANGCHAIN_ENDPOINT"] = self.langsmith_config.LANGCHAIN_ENDPOINT

    def _init_langfuse(self) -> None:
        """Инициализация Langfuse трейсинга"""
        if not self.langfuse_config.USE_LANGFUSE:
            return

        try:
            Langfuse(
                public_key=self.langfuse_config.LANGFUSE_PUBLIC_KEY,
                secret_key=self.langfuse_config.LANGFUSE_SECRET_KEY,
                host=self.langfuse_config.LANGFUSE_BASE_URL,
            )
            self.client = get_client()
            self.langfuse_handler = CallbackHandler()
            self.callbacks.append(self.langfuse_handler)

        except Exception:
            pass