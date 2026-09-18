from contextlib import asynccontextmanager

from db.database import global_db_manager
from db.sqlalchemy.web_conversations import WebConversationRepository


@asynccontextmanager
async def conversation_repository():
    session = global_db_manager.get_session()
    try:
        yield WebConversationRepository(session)
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


def conversation_dict(conversation):
    return {
        "id": conversation.id,
        "user_id": conversation.user_id,
        "title": conversation.title,
        "thread_id": conversation.thread_id,
        "archived": conversation.archived_at is not None,
        "created_at": conversation.created_at,
        "updated_at": conversation.updated_at,
    }


def message_dict(message):
    return {
        "id": message.id,
        "conversation_id": message.conversation_id,
        "role": message.role,
        "content": message.content,
        "status": message.status,
        "client_message_id": message.client_message_id,
        "created_at": message.created_at,
    }
