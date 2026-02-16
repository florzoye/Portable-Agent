import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from dotenv import load_dotenv, find_dotenv

_ENV_LOADED = False
if not _ENV_LOADED:
    load_dotenv(find_dotenv())
    _ENV_LOADED = True

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

class BaseConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=os.path.join(BASE_DIR, ".env"),
        env_file_encoding="utf-8",
    )