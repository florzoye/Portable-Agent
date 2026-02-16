import os
from .base_config import BaseConfig, BASE_DIR

class DBConfig(BaseConfig):
    DB_HOST: str
    DB_PORT: int
    DB_USER: str
    DB_NAME: str
    DB_TYPE: str
    DB_PASSWORD: str
    SQLITE_PATH: str
    DB_DEBUG: bool = False

    UPLOAD_DIR: str = os.path.join(BASE_DIR, 'app/uploads')
    STATIC_DIR: str = os.path.join(BASE_DIR, 'app/static')
    
    @property
    def url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.DB_USER}:{self.DB_PASSWORD}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        )