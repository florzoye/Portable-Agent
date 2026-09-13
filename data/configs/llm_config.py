from .base_config import BaseConfig
   
class BaseLLMConfig(BaseConfig):
    TEMPERATURE: float
    MAX_TOKENS: int
    VERBOSE: bool
    TIMEOUT: int
    TOP_P: float
    CONTEXT_TRIGGER_TOKENS: int = 12000
    CONTEXT_KEEP_MESSAGES: int = 12
    CONTEXT_MAX_TOOL_ARG_LENGTH: int = 2000
