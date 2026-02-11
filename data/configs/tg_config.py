import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv())

class TelegramSettings(BaseSettings):
    BOT_TOKEN: str
    session_name: str = "tg_session"

    BASE_DIR: str = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    model_config = SettingsConfigDict(
        env_file=os.path.join(BASE_DIR, ".env"),
        env_file_encoding="utf-8",
    )

    @property
    def send_message_url(self) -> str:
        return f"https://api.telegram.org/bot{self.BOT_TOKEN}/sendMessage"