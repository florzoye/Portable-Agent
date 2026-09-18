from datetime import datetime
from typing import Annotated, Optional
from sqlalchemy import (
    Boolean,
    Integer,
    String,
    DateTime,
    func,
    ForeignKey,
    Index,
    Text,
    text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

strnullable = Annotated[Optional[str], mapped_column(String, nullable=True)]
textnullable = Annotated[Optional[str], mapped_column(Text, nullable=True)]


class Base(DeclarativeBase):
    def __repr__(self):
        cols = self.__table__.columns.keys()
        return f'{self.__class__.__name__}(' + ', '.join(f'{c}={getattr(self, c)!r}' for c in cols) + ')'


class Users(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tg_id: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    tg_nick: Mapped[strnullable]
    email: Mapped[strnullable]
    google_id: Mapped[strnullable] = mapped_column(String, nullable=True, index=True)  # + index

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )

    google_tokens: Mapped[list["GoogleToken"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        order_by="GoogleToken.created_at.desc()",  
        lazy="noload"  
    )


class GoogleToken(Base):
    __tablename__ = "google_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    access_token: Mapped[str] = mapped_column(Text, nullable=False)
    refresh_token: Mapped[textnullable]
    token_expiry: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)  
    token_type: Mapped[strnullable]
    scopes: Mapped[textnullable]

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )

    user: Mapped["Users"] = relationship(back_populates="google_tokens", lazy="noload")


class ModelProfile(Base):
    __tablename__ = "model_profiles"
    __table_args__ = (
        Index(
            "uq_model_profiles_one_active_per_user",
            "user_id",
            unique=True,
            postgresql_where=text("is_active = true"),
            sqlite_where=text("is_active = 1"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.tg_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    model_name: Mapped[str] = mapped_column(String(200), nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    encrypted_api_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class WebConversation(Base):
    """A browser conversation owned by exactly one authenticated web user."""

    __tablename__ = "web_conversations"
    __table_args__ = (Index("ix_web_conversations_user_updated", "user_id", "updated_at"),)

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.tg_id", ondelete="CASCADE"), nullable=False, index=True
    )
    thread_id: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    title: Mapped[str] = mapped_column(
        String(200), nullable=False, default="New conversation", server_default="New conversation"
    )
    archived_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    messages: Mapped[list["WebMessage"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan", lazy="noload"
    )


class WebMessage(Base):
    __tablename__ = "web_messages"
    __table_args__ = (
        UniqueConstraint("conversation_id", "client_message_id", name="uq_web_messages_client_id"),
        Index("ix_web_messages_conversation_created", "conversation_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("web_conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="complete", server_default="complete"
    )
    client_message_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    conversation: Mapped["WebConversation"] = relationship(back_populates="messages", lazy="noload")