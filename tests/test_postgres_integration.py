import asyncio
import os
import unittest
from unittest import mock

from cryptography.fernet import Fernet
from sqlalchemy import func, insert, inspect, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from db.sqlalchemy.migrations import check_database, migrate_database
from db.sqlalchemy.model_profiles_crud import ModelProfilesORM
from db.sqlalchemy.models import Base, ModelProfile, Users
from src.services.models.providers import ModelProvider


POSTGRES_TEST_URL = os.getenv("POSTGRES_TEST_URL")


@unittest.skipUnless(
    POSTGRES_TEST_URL,
    "Set POSTGRES_TEST_URL to run PostgreSQL integration tests",
)
class PostgreSQLIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine(POSTGRES_TEST_URL, pool_pre_ping=True)
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.drop_all)
            await connection.execute(text("DROP TABLE IF EXISTS schema_migrations"))
        async with self.engine.begin() as connection:
            await migrate_database(
                self.engine,
                Base.metadata,
                extra_tables=("users", "google_tokens", "model_profiles"),
            )
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)

    async def asyncTearDown(self):
        await self.engine.dispose()

    async def test_migration_and_required_schema_are_idempotent(self):
        status = await check_database(
            self.engine,
            required_tables=("users", "google_tokens", "model_profiles"),
        )
        self.assertEqual(status.current_version, 2)
        self.assertFalse(status.upgrade_required)
        self.assertTrue(
            await migrate_database(
                self.engine,
                Base.metadata,
                extra_tables=("users", "google_tokens", "model_profiles"),
            )
        )

    async def test_existing_version_one_database_receives_active_index_upgrade(self):
        async with self.engine.begin() as connection:
            await connection.execute(
                text("DROP INDEX uq_model_profiles_one_active_per_user")
            )
            await connection.execute(
                text("DELETE FROM schema_migrations WHERE version = 2")
            )
        status = await check_database(self.engine)
        self.assertEqual(status.current_version, 1)
        self.assertTrue(status.upgrade_required)
        self.assertFalse(
            await migrate_database(
                self.engine,
                Base.metadata,
                extra_tables=("users", "google_tokens", "model_profiles"),
            )
        )
        async with self.engine.connect() as connection:
            indexes = await connection.run_sync(
                lambda sync_connection: {
                    index["name"]
                    for index in inspect(sync_connection).get_indexes(
                        "model_profiles"
                    )
                }
            )
        self.assertIn("uq_model_profiles_one_active_per_user", indexes)

    async def test_foreign_key_and_encrypted_key_round_trip(self):
        with mock.patch.dict(
            os.environ,
            {"TOKEN_ENCRYPTION_KEY": Fernet.generate_key().decode()},
        ):
            async with self.sessions() as session:
                await session.execute(insert(Users).values(tg_id=1001))
                await session.commit()
                repository = ModelProfilesORM(session)
                profile = await repository.create(
                    1001,
                    ModelProvider.OPENAI,
                    "gpt-4o-mini",
                    "Private OpenAI",
                    "secret-key",
                )
                await session.commit()
                self.assertEqual(
                    await repository.get_api_key(1001, profile.id),
                    "secret-key",
                )
                with self.assertRaises(Exception):
                    await repository.create(
                        9999,
                        ModelProvider.OPENAI,
                        "gpt-4o-mini",
                        "Invalid owner",
                        "secret-key",
                    )
                    await session.commit()
                await session.rollback()

    async def test_concurrent_activation_keeps_one_active_profile(self):
        with mock.patch.dict(
            os.environ,
            {"TOKEN_ENCRYPTION_KEY": Fernet.generate_key().decode()},
        ):
            async with self.sessions() as session:
                await session.execute(insert(Users).values(tg_id=2001))
                await session.commit()
                repository = ModelProfilesORM(session)
                first = await repository.create(
                    2001, ModelProvider.OLLAMA, "model-a", "Model A", None
                )
                second = await repository.create(
                    2001, ModelProvider.OLLAMA, "model-b", "Model B", None
                )
                await session.commit()

            async def activate(profile_id: int):
                async with self.sessions() as concurrent_session:
                    await ModelProfilesORM(concurrent_session).activate(
                        2001, profile_id
                    )
                    await concurrent_session.commit()

            results = await asyncio.gather(
                activate(first.id),
                activate(second.id),
            )
            self.assertEqual(results, [None, None])
            async with self.sessions() as session:
                active_count = await session.scalar(
                    select(func.count(ModelProfile.id))
                    .where(
                        ModelProfile.user_id == 2001,
                        ModelProfile.is_active.is_(True),
                    )
                )
                self.assertEqual(active_count, 1)
