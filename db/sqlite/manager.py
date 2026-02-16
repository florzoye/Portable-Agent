import aiosqlite
import logging
from typing import List, Dict, Optional

class AsyncDatabaseManager:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._conn: Optional[aiosqlite.Connection] = None
        self.logger = logging.getLogger(self.__class__.__name__)

    async def connect(self):
        if self._conn is None:
            try:
                self._conn = await aiosqlite.connect(self.db_path)
                self._conn.row_factory = aiosqlite.Row
                self.logger.debug(f"✅ Подключено к SQLite: {self.db_path}")
            except Exception as e:
                self.logger.error(f"❌ Ошибка подключения к SQLite: {e}")
                raise

    async def close(self):
        try:
            if self._conn is not None:
                await self._conn.close()
                self._conn = None
                self.logger.info("✅ Соединение с SQLite закрыто")
        except Exception as e:
            self.logger.error(f"⚠️ Ошибка при закрытии SQLite: {e}")

    async def execute(self, query: str, params: Dict = None):
        await self.connect()
        try:
            if params:
                await self._conn.execute(query, params)
            else:
                await self._conn.execute(query)
            await self._conn.commit()
        except Exception as e:
            self.logger.error(f"❌ Ошибка выполнения запроса: {e}\nQuery: {query}")
            raise

    async def fetchall(self, query: str, params: Dict = None) -> List[Dict]:
        await self.connect()
        try:
            cursor = await self._conn.execute(query, params or {})
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]
        except Exception as e:
            self.logger.error(f"❌ Ошибка fetchall: {e}\nQuery: {query}")
            raise

    async def fetchone(self, query: str, params: Dict = None) -> Optional[Dict]:
        await self.connect()
        try:
            cursor = await self._conn.execute(query, params or {})
            row = await cursor.fetchone()
            return dict(row) if row else None
        except Exception as e:
            self.logger.error(f"❌ Ошибка fetchone: {e}\nQuery: {query}")
            raise
    
    @property
    def is_connected(self) -> bool:
        return self._conn is not None