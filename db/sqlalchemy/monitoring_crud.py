import json
from pathlib import Path
from typing import Any

from sqlalchemy import Float, Integer, String, Text, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Mapped, mapped_column

from db.monitoring_protocol import MonitoringBase
from db.sqlalchemy.models import Base
from db.sqlalchemy.migrations import migrate_database


class MonitoringEvent(Base):
    __tablename__ = "monitoring_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    payload: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[float] = mapped_column(Float, nullable=False, index=True)


class MonitoringORM(MonitoringBase):
    def __init__(self, database_url: str, max_events: int = 1000):
        if database_url.startswith("sqlite+aiosqlite:///"):
            database_path = Path(database_url.removeprefix("sqlite+aiosqlite:///"))
            database_path.parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_async_engine(database_url)
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)
        self.max_events = max_events

    async def create_tables(self) -> bool:
        return await migrate_database(
            self.engine,
            MonitoringEvent.metadata,
            extra_tables=("monitoring_events",),
        )

    async def record(self, payload: dict[str, Any]) -> None:
        async with self.sessions() as session:
            session.add(MonitoringEvent(
                event=payload["event"],
                payload=json.dumps(payload, default=str),
                created_at=payload["timestamp"],
            ))
            await session.commit()
            event_ids = await session.scalars(
                select(MonitoringEvent.id)
                .order_by(MonitoringEvent.id.desc())
                .offset(self.max_events)
            )
            ids_to_delete = list(event_ids)
            if ids_to_delete:
                await session.execute(
                    MonitoringEvent.__table__.delete().where(
                        MonitoringEvent.id.in_(ids_to_delete)
                    )
                )
                await session.commit()

    async def stats(self) -> dict[str, Any]:
        async with self.sessions() as session:
            rows = await session.scalars(
                select(MonitoringEvent.payload)
                .order_by(MonitoringEvent.id.desc())
                .limit(50)
            )
            events = await session.execute(
                select(MonitoringEvent.event, func.count()).group_by(MonitoringEvent.event)
            )
            payloads = [json.loads(payload) for payload in reversed(list(rows))]
            counters = dict(events.all())
            tokens: dict[str, int] = {}
            for payload in payloads:
                model = payload.get("model")
                if model:
                    tokens[model] = tokens.get(model, 0) + int(
                        payload.get("total_tokens")
                        or payload.get("input_tokens", 0) + payload.get("output_tokens", 0)
                    )
            return {
                "events": counters,
                "tokens_by_model": tokens,
                "recent_events": payloads,
            }

    async def close(self) -> None:
        await self.engine.dispose()
