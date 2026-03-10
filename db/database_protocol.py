from datetime import datetime
from typing import Optional, List
from abc import ABC, abstractmethod

from src.models import UserModel, TokenModel


class UsersBase(ABC):
    @abstractmethod
    async def create_tables(self) -> bool:
        """Create user tables"""
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
        Add a new user.

        Returns:
            Optional[UserModel]: UserModel for SQLite or Users for PostgreSQL
        """
        ...

    @abstractmethod
    async def get_user_by_tg_id(self, tg_id: int) -> Optional[UserModel]:
        """Get a user by Telegram ID"""
        ...

    @abstractmethod
    async def get_user_by_id(self, user_id: int) -> Optional[UserModel]:
        """Get a user by internal ID"""
        ...

    @abstractmethod
    async def get_user_by_google_id(self, google_id: str) -> Optional[UserModel]:
        """Get a user by Google ID"""
        ...

    @abstractmethod
    async def get_all_users(self) -> List[UserModel]:
        """Get all users"""
        ...

    @abstractmethod
    async def user_exists(self, tg_id: int) -> bool:
        """Check if a user exists by Telegram ID"""
        ...

    @abstractmethod
    async def google_id_exists(self, google_id: str) -> bool:
        """Check if a user exists by Google ID"""
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
        Update user data.

        Note:
            SQLite uses named parameters.
            PostgreSQL can use **kwargs.
        """
        ...

    @abstractmethod
    async def delete_user(self, tg_id: int) -> bool:
        """Delete a user by Telegram ID"""
        ...

    @abstractmethod
    async def delete_all_tables(self) -> bool:
        """Delete all tables (used for testing)"""
        ...


class GoogleTokensBase(ABC):
    """Base interface for working with Google tokens"""

    @abstractmethod
    async def create_tables(self) -> bool:
        """Create token tables"""
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
        Save or update a token.

        Note:
            scopes is used only in PostgreSQL.
        """
        ...

    @abstractmethod
    async def get_token(self, user_id: int) -> Optional[TokenModel]:
        """
        Get a token by user_id.

        Returns:
            Optional[TokenModel]: TokenModel for SQLite or GoogleToken for PostgreSQL
        """
        ...

    @abstractmethod
    async def get_token_by_tg_id(self, tg_id: int) -> Optional[TokenModel]:
        """
        Get a token by Telegram ID.

        Note:
            Requires a JOIN with the users table.
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
        """Update an existing token"""
        ...

    @abstractmethod
    async def delete_token(self, user_id: int) -> bool:
        """Delete a user's token"""
        ...

    @abstractmethod
    async def token_exists(self, user_id: int) -> bool:
        """Check if a token exists"""
        ...

    @abstractmethod
    async def delete_all_tables(self) -> bool:
        """Delete token tables (used for testing)"""
        ...