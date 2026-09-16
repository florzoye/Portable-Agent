from .base_config import BaseConfig


class TenantLimitsConfig(BaseConfig):
    MAX_MODEL_PROFILES: int = 10
    MAX_MODEL_NAME_LENGTH: int = 200
    MAX_DISPLAY_NAME_LENGTH: int = 200
