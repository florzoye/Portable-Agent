from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.sqlalchemy.models import WebConversation, WebMessage


class WebConversationRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, user_id: int, title: str = "New conversation") -> WebConversation:
        conversation = WebConversation(
            id=str(uuid4()),
            user_id=user_id,
            thread_id=str(uuid4()),
            title=title.strip()[:200] or "New conversation",
        )
        self.session.add(conversation)
        await self.session.flush()
        return conversation

    async def get(self, user_id: int, conversation_id: str) -> Optional[WebConversation]:
        result = await self.session.execute(
            select(WebConversation).where(
                WebConversation.id == conversation_id, WebConversation.user_id == user_id
            )
        )
        return result.scalar_one_or_none()

    async def list(
        self, user_id: int, *, include_archived: bool = False, limit: int = 50, offset: int = 0
    ) -> list[WebConversation]:
        query = select(WebConversation).where(WebConversation.user_id == user_id)
        if not include_archived:
            query = query.where(WebConversation.archived_at.is_(None))
        result = await self.session.execute(
            query.order_by(WebConversation.updated_at.desc())
            .limit(min(max(limit, 1), 100))
            .offset(max(offset, 0))
        )
        return list(result.scalars())

    async def rename(self, user_id: int, conversation_id: str, title: str) -> Optional[WebConversation]:
        conversation = await self.get(user_id, conversation_id)
        if conversation:
            conversation.title = title.strip()[:200] or "New conversation"
            await self.session.flush()
        return conversation

    async def archive(self, user_id: int, conversation_id: str) -> Optional[WebConversation]:
        conversation = await self.get(user_id, conversation_id)
        if conversation:
            conversation.archived_at = datetime.now(timezone.utc)
            await self.session.flush()
        return conversation

    async def delete(self, user_id: int, conversation_id: str) -> bool:
        result = await self.session.execute(
            delete(WebConversation).where(
                WebConversation.id == conversation_id, WebConversation.user_id == user_id
            )
        )
        return result.rowcount > 0

    async def get_message_by_client_id(
        self, user_id: int, conversation_id: str, client_message_id: str
    ) -> Optional[WebMessage]:
        result = await self.session.execute(
            select(WebMessage)
            .join(WebConversation)
            .where(
                WebConversation.user_id == user_id,
                WebMessage.conversation_id == conversation_id,
                WebMessage.client_message_id == client_message_id,
            )
        )
        return result.scalar_one_or_none()

    async def add_message(
        self,
        user_id: int,
        conversation_id: str,
        role: str,
        content: str,
        client_message_id: str | None = None,
        status: str = "complete",
    ) -> Optional[WebMessage]:
        conversation = await self.get(user_id, conversation_id)
        if not conversation:
            return None
        if client_message_id:
            existing = await self.get_message_by_client_id(user_id, conversation_id, client_message_id)
            if existing:
                return existing
        message = WebMessage(
            id=str(uuid4()),
            conversation_id=conversation_id,
            role=role,
            content=content,
            status=status,
            client_message_id=client_message_id,
        )
        self.session.add(message)
        conversation.updated_at = datetime.now(timezone.utc)
        await self.session.flush()
        return message

    async def update_message(
        self,
        user_id: int,
        message_id: str,
        *,
        content: str | None = None,
        status: str | None = None,
    ) -> Optional[WebMessage]:
        result = await self.session.execute(
            select(WebMessage)
            .join(WebConversation)
            .where(WebMessage.id == message_id, WebConversation.user_id == user_id)
        )
        message = result.scalar_one_or_none()
        if message is None:
            return None
        if content is not None:
            message.content = content
        if status is not None:
            message.status = status
        await self.session.flush()
        return message

    async def messages(
        self, user_id: int, conversation_id: str, limit: int = 50, before: str | None = None
    ) -> list[WebMessage]:
        query = select(WebMessage).join(WebConversation).where(
            WebConversation.user_id == user_id, WebMessage.conversation_id == conversation_id
        )
        if before:
            query = query.where(WebMessage.created_at < before)
        result = await self.session.execute(
            query.order_by(WebMessage.created_at.desc()).limit(min(max(limit, 1), 100))
        )
        return list(reversed(result.scalars().all()))
