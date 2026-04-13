from loguru import logger
from threading import Lock
from src.enum import DatabaseType

from utils.metaclasses import SingletonLockMeta   
from src.exceptions import ConfigNotInitializedError
from langchain_core.runnables import RunnableConfig


class ConfigRegistry(metaclass=SingletonLockMeta):
    _initialized = False
    _lock = Lock()

    def __init__(self):
        with self._lock:
            if self._initialized:
                return

            # config without depends
            self._google_config = None
            self._db_config = None
            self._tg_settings = None
            self._base_llm_config = None
            self._ollama_config = None
            self._ports_config = None
            self._openai_config = None
            self._xai_config = None

            # config with depends
            self._redis_client = None
            self._celery_app = None
            self._runnable_config = None
            self._callback_service = None

    def _init_simple_configs(self):
        """init simple config """
        from data.configs.google_config import GoogleSettings
        from data.configs.database_config import DBConfig
        from data.configs.tg_config import TelegramSettings
        from data.configs.llm_config import BaseLLMConfig
        from data.configs.ollama_config import OllamaConfig
        from data.configs.openai_config import OpenAIConfig
        from data.configs.xai_config import XAIConfig

        self._google_config = GoogleSettings()
        logger.success('✓ GoogleSettings init!')

        self._db_config = DBConfig()
        logger.success('✓ DBConfig init!')

        if self._db_config.DB_TYPE not in [DatabaseType.SQLITE.value, DatabaseType.POSTGRESQL.value]:
            raise ConfigNotInitializedError(f'Неизвестный тип базы данных: {self._db_config.DB_TYPE}')
        
        self._tg_settings = TelegramSettings()
        logger.success('✓ TelegramSettings init!')

        self._base_llm_config = BaseLLMConfig()
        logger.success('✓ BaseLLMConfig init!')

        self._ollama_config = OllamaConfig()
        logger.success('✓ OllamaConfig init!')
        
        self._openai_config = OpenAIConfig()
        logger.success('✓ OpenAIConfig init!')

        self._xai_config = XAIConfig()
        logger.success('✓ XAIConfig init!')

    def _init_brokers(self):
        """initializing brokers and queue"""
        from data.configs.redis_config import RedisSettings
        from redis.asyncio import Redis
        from celery import Celery

        settings = RedisSettings()
        redis_url = f"redis://:{settings.REDIS_PASSWORD}@{settings.REDIS_HOST}:{settings.REDIS_PORT}/0"

        self._celery_app = Celery("celery_worker", broker=redis_url, backend=redis_url)
        self._celery_app.conf.update(
            task_serializer='json',
            result_serializer='json',
            accept_content=['json'],
            enable_utc=True,
            timezone='Europe/Moscow',
            broker_connection_retry_on_startup=True,
            task_acks_late=True,
            worker_prefetch_multiplier=1,
        )

        self._redis_client = Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            db=0,
            password=settings.REDIS_PASSWORD,
            decode_responses=True,  
        )

        logger.success('✓ REDIS_CLIENT and CELERY_APP init!')

    def _init_services(self):
        """init config with depends"""
        from data.configs.callbacks_config import GlobalCallbacksService
        
        self._callback_service = GlobalCallbacksService()
        self._callback_service.initialize()
        
        if self._callback_service.langsmith_config.LANGCHAIN_TRACING_V2:
            logger.success(
                f'✓ LangSmith ENABLED | project={self._callback_service.langsmith_config.LANGCHAIN_PROJECT}'
            )
        else:
            logger.success('✓ LangSmith tracing DISABLED')
            
        if self._callback_service.langfuse_config.USE_LANGFUSE:
            if self._callback_service.langfuse_handler:
                logger.success('✓ Langfuse initialized')
            else:
                logger.warning('⚠ Langfuse init failed')
        else:
            logger.info('✓ Langfuse disabled')
        
        logger.success('✓ CALLBACK_SERVICE init!')

        self._runnable_config = RunnableConfig(
            callbacks=self._callback_service.callbacks
        )
        logger.success('✓ RUNNABLE_CONFIG init!')

    def initialize(self):
        """Full initializing"""
        with self._lock:
            if self._initialized:
                logger.warning('⚠ Configuration init!, pass retry init')
                return

            logger.info('Start initializing the configuration...')
            self._init_simple_configs()
            self._init_brokers()
            self._init_services()
            self._initialized = True
            logger.success('🎉 All configuration succes init!')

    @property
    def GOOGLE_CONFIG(self):
        self._check_initialized()
        return self._google_config

    @property
    def DB_CONFIG(self):
        self._check_initialized()
        return self._db_config

    @property
    def TG_SETTINGS(self):
        self._check_initialized()
        return self._tg_settings

    @property
    def redis_client(self):
        self._check_initialized()
        return self._redis_client

    @property
    def celery_app(self):
        self._check_initialized()
        return self._celery_app

    @property
    def BASE_LLM_CONFIG(self):
        self._check_initialized()
        return self._base_llm_config
    
    @property
    def OLLAMA_CONFIG(self):
        self._check_initialized()
        return self._ollama_config

    @property
    def PORTS_CONFIG(self):
        self._check_initialized()
        return self._ports_config

    @property
    def CALLBACK_SERVICE(self):
        self._check_initialized()
        return self._callback_service
    
    @property
    def RUNNABLE_CONFIG(self):
        self._check_initialized()
        return self._runnable_config
    
    @property
    def OPENAI_CONFIG(self):
        self._check_initialized()
        return self._openai_config
    
    @property
    def XAI_CONFIG(self):
        self._check_initialized()
        return self._xai_config

    @property
    def is_initialized(self) -> bool:
        return self._initialized

    def _check_initialized(self):
        if not self._initialized:
            raise ConfigNotInitializedError()


def init():
    ConfigRegistry().initialize()


def get_config() -> ConfigRegistry:
    instance = ConfigRegistry()
    if not instance.is_initialized:
        raise ConfigNotInitializedError()
    return instance

__all__ = ['init', 'get_config']