import asyncio
from db.base import Base
from db.session import engine
# Импорт моделей, чтобы Base их увидел
from db.models import User, GoogleToken

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("✅ Таблицы созданы")

if __name__ == "__main__":
    asyncio.run(init_db())
