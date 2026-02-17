from datetime import datetime
from abc import ABC, abstractmethod
from typing import Optional, Any, List

from src.models.user_model import UserModel
from src.models.token_model import TokenModel

class UsersBase(ABC):
    """Базовый интерфейс для работы с пользователями"""

    @abstractmethod
    async def create_tables(self) -> bool:
        """Создать таблицу пользователей"""
        ...

    @abstractmethod
    async def add_user(
        self,
        tg_id: int,
        *,
        tg_nick: Optional[str] = None,
        email: Optional[str] = None,
        google_id: Optional[str] = None
    ) -> Optional[UserModel]:
        """
        Добавить пользователя
        
        Returns:
            Optional[Any]: UserModel для SQLite или Users для PostgreSQL
        """
        ...

    @abstractmethod
    async def get_user_by_tg_id(self, tg_id: int) -> Optional[UserModel]:
        """Получить пользователя по Telegram ID"""
        ...

    @abstractmethod
    async def get_user_by_id(self, user_id: int) -> Optional[UserModel]:
        """Получить пользователя по внутреннему ID"""
        ...

    @abstractmethod
    async def get_user_by_google_id(self, google_id: str) -> Optional[UserModel]:
        """Получить пользователя по Google ID"""
        ...

    @abstractmethod
    async def get_all_users(self) -> List[UserModel]:
        """Получить всех пользователей"""
        ...

    @abstractmethod
    async def user_exists(self, tg_id: int) -> bool:
        """Проверить существование пользователя по Telegram ID"""
        ...

    @abstractmethod
    async def google_id_exists(self, google_id: str) -> bool:
        """Проверить существование пользователя по Google ID"""
        ...

    @abstractmethod
    async def update_user(
        self,
        tg_id: int,
        *,
        tg_nick: Optional[str] = None,
        email: Optional[str] = None,
        google_id: Optional[str] = None
    ) -> bool:
        """
        Обновить данные пользователя
        
        Note: Для SQLite используются именованные параметры
              Для PostgreSQL можно использовать **kwargs
        """
        ...

    @abstractmethod
    async def delete_user(self, tg_id: int) -> bool:
        """Удалить пользователя по Telegram ID"""
        ...

    @abstractmethod
    async def delete_all_tables(self) -> bool:
        """Удалить все таблицы (для тестов)"""
        ...


class GoogleTokensBase(ABC):
    """Базовый интерфейс для работы с Google токенами"""

    @abstractmethod
    async def create_tables(self) -> bool:
        """Создать таблицу токенов"""
        ...

    @abstractmethod
    async def save_token(
        self,
        user_id: int,
        access_token: str,
        refresh_token: Optional[str] = None,
        token_type: str = "Bearer",
        token_expiry: Optional[datetime] = None,
        scopes: Optional[str] = None
    ) -> bool:
        """
        Сохранить или обновить токен
        
        Note: scopes используется только в PostgreSQL
        """
        ...

    @abstractmethod
    async def get_token(self, user_id: int) -> Optional[TokenModel]:
        """
        Получить токен по user_id
        
        Returns:
            Optional[TokenModel]: TokenModel для SQLite или GoogleToken для PostgreSQL
        """
        ...

    @abstractmethod
    async def get_token_by_tg_id(self, tg_id: int) -> Optional[TokenModel]:
        """
        Получить токен по Telegram ID
        
        Note: Требует JOIN с таблицей users
        """
        ...

    @abstractmethod
    async def update_token(
        self,
        user_id: int,
        *,
        access_token: Optional[str] = None,
        refresh_token: Optional[str] = None,
        token_expiry: Optional[datetime] = None
    ) -> bool:
        """Обновить существующий токен"""
        ...

    @abstractmethod
    async def delete_token(self, user_id: int) -> bool:
        """Удалить токен пользователя"""
        ...

    @abstractmethod
    async def token_exists(self, user_id: int) -> bool:
        """Проверить существование токена"""
        ...

    @abstractmethod
    async def delete_all_tables(self) -> bool:
        """Удалить таблицу токенов (для тестов)"""
        ...