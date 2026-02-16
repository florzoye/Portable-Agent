from .base_config import BaseConfig

class RedisSettings(BaseConfig):
    REDIS_PORT: int
    REDIS_PASSWORD: str
    REDIS_HOST: str