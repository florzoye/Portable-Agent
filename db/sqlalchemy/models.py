from typing import Annotated
from sqlalchemy import Integer, String, DateTime, func, ForeignKey, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

strnullable = Annotated[str | None, mapped_column(String, nullable=True)]
textnullable = Annotated[str | None, mapped_column(Text, nullable=True)]

class Base(DeclarativeBase):
    def __repr__(self):
        col = [col for col in self.__table__.columns.keys()]
        return f'{self.__class__.__name__}(' + ', '.join(f'{c}={getattr(self, c)!r}' for c in col) + ')'

class Users(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True) 
    tg_id: Mapped[int] = mapped_column(Integer, unique=True, index=True)  
    tg_nick: Mapped[strnullable]
    email: Mapped[strnullable] 
    google_id: Mapped[strnullable]  
    
    google_tokens: Mapped[list["GoogleToken"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        order_by="GoogleToken.created_at.desc()"
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
    token_expiry: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    token_type: Mapped[strnullable] 
    scopes: Mapped[textnullable]  
    
    created_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True), 
        server_default=func.now(),
        nullable=False
    )
    updated_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )
    
    user: Mapped["Users"] = relationship(back_populates="google_tokens")