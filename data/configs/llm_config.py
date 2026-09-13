from .base_config import BaseConfig
   
class BaseLLMConfig(BaseConfig):
    TEMPERATURE: float
    MAX_TOKENS: int
    VERBOSE: bool
    TIMEOUT: int
    TOP_P: float
