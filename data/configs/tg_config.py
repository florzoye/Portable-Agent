from .base_config import BaseConfig
from pydantic import field_validator

class TelegramSettings(BaseConfig):
    BOT_TOKEN: str
    session_name: str = "tg_session"
    TELEGRAM_PROXY: str | None = None

    @field_validator("TELEGRAM_PROXY")
    @classmethod
    def validate_proxy(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        if not value.startswith(("http://", "https://", "socks5://", "socks5h://")):
            raise ValueError(
                "TELEGRAM_PROXY must use http, https, socks5, or socks5h scheme"
            )
        return value

    @property
    def send_message_url(self) -> str:
        return f"https://api.telegram.org/bot{self.BOT_TOKEN}/sendMessage"