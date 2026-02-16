from .base_config import BaseConfig

class TelegramSettings(BaseConfig):
    BOT_TOKEN: str
    session_name: str = "tg_session"

    @property
    def send_message_url(self) -> str:
        return f"https://api.telegram.org/bot{self.BOT_TOKEN}/sendMessage"