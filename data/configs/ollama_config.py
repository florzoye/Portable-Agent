from .base_config import BaseConfig

class OllamaConfig(BaseConfig):
    OLLAMA_MODEL: str
    OLLAMA_HOST: str = "http://host.docker.internal:11434"