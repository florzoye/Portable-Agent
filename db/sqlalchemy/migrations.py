from collections.abc import Iterable

from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.schema import MetaData


SCHEMA_VERSION = 1
VERSION_TABLE = "schema_migrations"


async def migrate_database(
    engine: AsyncEngine,
    metadata: MetaData,
    *,
    version: int = SCHEMA_VERSION,
    extra_tables: Iterable[str] = (),
) -> bool:
    """Bring a database to the registered schema version.

    The migration is idempotent: it creates the version table and any missing
    tables, then records the applied version. Future schema changes should add
    a new versioned migration instead of changing this baseline silently.
    """
    async with engine.begin() as connection:
        await connection.run_sync(
            lambda sync_connection: metadata.create_all(sync_connection)
        )
        await connection.run_sync(
            lambda sync_connection: _ensure_version_table(
                sync_connection,
                extra_tables=extra_tables,
            )
        )
        current = await connection.scalar(
            text(f"SELECT version FROM {VERSION_TABLE} ORDER BY version DESC LIMIT 1")
        )
        if current is not None and int(current) > version:
            raise RuntimeError(
                f"Database schema version {current} is newer than supported {version}"
            )
        if current != version:
            await connection.execute(
                text(
                    f"INSERT INTO {VERSION_TABLE} (version) VALUES (:version)"
                ),
                {"version": version},
            )
    return current == version


def _ensure_version_table(sync_connection, *, extra_tables: Iterable[str]) -> None:
    inspector = inspect(sync_connection)
    if VERSION_TABLE not in inspector.get_table_names():
        sync_connection.execute(
            text(
                f"CREATE TABLE {VERSION_TABLE} "
                "(version INTEGER PRIMARY KEY, applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
            )
        )
    for table_name in extra_tables:
        if table_name not in inspector.get_table_names():
            raise RuntimeError(f"Required table was not created: {table_name}")
