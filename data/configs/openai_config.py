from .base_config import BaseConfig

class OpenAIConfig(BaseConfig):
    OPENAI_MODEL: str
    OPENAI_API_KEY: str