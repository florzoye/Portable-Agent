from collections.abc import Callable, Iterable
from dataclasses import dataclass

from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.schema import MetaData


SCHEMA_VERSION = 2
VERSION_TABLE = "schema_migrations"


@dataclass(frozen=True, slots=True)
class MigrationStatus:
    current_version: int
    target_version: int
    upgrade_required: bool


Migration = Callable[[object, MetaData], None]


def _create_baseline(sync_connection, metadata: MetaData) -> None:
    metadata.create_all(sync_connection)


def _add_active_profile_index(sync_connection, metadata: MetaData) -> None:
    metadata.create_all(sync_connection)
    sync_connection.execute(
        text(
            "CREATE UNIQUE INDEX IF NOT EXISTS "
            "uq_model_profiles_one_active_per_user "
            "ON model_profiles (user_id) "
            "WHERE is_active = true"
        )
    )


MIGRATIONS: dict[int, Migration] = {
    1: _create_baseline,
    2: _add_active_profile_index,
}


async def check_database(
    engine: AsyncEngine,
    *,
    version: int = SCHEMA_VERSION,
    required_tables: Iterable[str] = (),
) -> MigrationStatus:
    async with engine.connect() as connection:
        def read_version(sync_connection):
            if VERSION_TABLE not in inspect(sync_connection).get_table_names():
                return None
            return sync_connection.execute(
                text(
                    f"SELECT version FROM {VERSION_TABLE} "
                    "ORDER BY version DESC LIMIT 1"
                )
            ).scalar()

        current = await connection.run_sync(read_version)
        missing_tables = await connection.run_sync(
            lambda sync_connection: [
                table_name
                for table_name in required_tables
                if table_name not in inspect(sync_connection).get_table_names()
            ]
        )
    current_version = int(current or 0)
    if current_version > version:
        raise RuntimeError(
            f"Database schema version {current_version} is newer than supported {version}"
        )
    if missing_tables:
        raise RuntimeError(
            "Database is missing required tables: " + ", ".join(missing_tables)
        )
    return MigrationStatus(current_version, version, current_version < version)


async def migrate_database(
    engine: AsyncEngine,
    metadata: MetaData,
    *,
    version: int = SCHEMA_VERSION,
    extra_tables: Iterable[str] = (),
) -> bool:
    """Bring a database to the registered schema version."""
    async with engine.begin() as connection:
        await connection.run_sync(
            _ensure_version_table
        )
        current = await connection.scalar(
            text(f"SELECT version FROM {VERSION_TABLE} ORDER BY version DESC LIMIT 1")
        )
        current_version = int(current or 0)
        if current_version > version:
            raise RuntimeError(
                f"Database schema version {current_version} is newer than supported {version}"
            )
        for migration_version in range(current_version + 1, version + 1):
            migration = MIGRATIONS.get(migration_version)
            if migration is None:
                raise RuntimeError(
                    f"Migration {migration_version} is not registered"
                )
            await connection.run_sync(
                lambda sync_connection, migration=migration: migration(
                    sync_connection, metadata
                )
            )
            await connection.execute(
                text(
                    f"INSERT INTO {VERSION_TABLE} (version) VALUES (:version)"
                ),
                {"version": migration_version},
            )
        await connection.run_sync(
            lambda sync_connection: _ensure_required_tables(
                sync_connection, extra_tables
            )
        )
    return current_version == version


def _ensure_version_table(sync_connection) -> None:
    inspector = inspect(sync_connection)
    if VERSION_TABLE not in inspector.get_table_names():
        sync_connection.execute(
            text(
                f"CREATE TABLE {VERSION_TABLE} "
                "(version INTEGER PRIMARY KEY, applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
            )
        )
def _ensure_required_tables(sync_connection, extra_tables: Iterable[str]) -> None:
    inspector = inspect(sync_connection)
    for table_name in extra_tables:
        if table_name not in inspector.get_table_names():
            raise RuntimeError(f"Required table was not created: {table_name}")
