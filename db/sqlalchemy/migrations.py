from collections.abc import Callable, Iterable
from dataclasses import dataclass

from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.schema import MetaData


SCHEMA_VERSION = 4
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


def _add_web_conversation_tables(sync_connection, metadata: MetaData) -> None:
    metadata.create_all(
        sync_connection,
        tables=[
            metadata.tables["web_conversations"],
            metadata.tables["web_messages"],
        ],
    )


def _migrate_web_conversation_tenant_identity(sync_connection, metadata: MetaData) -> None:
    """Change stage-3 conversation ownership from users.id to users.tg_id."""
    inspector = inspect(sync_connection)
    if "web_conversations" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("web_conversations")}
    if "user_id" not in columns or "users" not in inspector.get_table_names():
        return

    if sync_connection.dialect.name == "sqlite":
        # SQLite cannot alter a referenced column constraint in place.  Rebuild
        # only this table and translate existing internal IDs before dropping it.
        sync_connection.execute(
            text(
                "CREATE TABLE web_conversations_stage4 ("
                "id VARCHAR(64) PRIMARY KEY, "
                "user_id INTEGER NOT NULL REFERENCES users(tg_id) ON DELETE CASCADE, "
                "thread_id VARCHAR(128) NOT NULL UNIQUE, "
                "title VARCHAR(200) NOT NULL, archived_at DATETIME NULL, "
                "created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, "
                "updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP)"
            )
        )
        sync_connection.execute(
            text(
                "INSERT INTO web_conversations_stage4 "
                "(id, user_id, thread_id, title, archived_at, created_at, updated_at) "
                "SELECT c.id, u.tg_id, c.thread_id, c.title, c.archived_at, c.created_at, c.updated_at "
                "FROM web_conversations c JOIN users u ON u.id = c.user_id"
            )
        )
        sync_connection.execute(text("DROP TABLE web_conversations"))
        sync_connection.execute(
            text("ALTER TABLE web_conversations_stage4 RENAME TO web_conversations")
        )
        sync_connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_web_conversations_user_updated "
                "ON web_conversations (user_id, updated_at)"
            )
        )
        sync_connection.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_web_conversations_thread_id "
                "ON web_conversations(thread_id)"
            )
        )
        return

    sync_connection.execute(
        text(
            "UPDATE web_conversations c SET user_id = u.tg_id "
            "FROM users u WHERE u.id = c.user_id"
        )
    )
    for constraint in ("web_conversations_user_id_fkey",):
        sync_connection.execute(
            text(f"ALTER TABLE web_conversations DROP CONSTRAINT IF EXISTS {constraint}")
        )
    sync_connection.execute(
        text(
            "ALTER TABLE web_conversations ADD CONSTRAINT "
            "web_conversations_user_id_fkey FOREIGN KEY (user_id) "
            "REFERENCES users(tg_id) ON DELETE CASCADE"
        )
    )


MIGRATIONS: dict[int, Migration] = {
    1: _create_baseline,
    2: _add_active_profile_index,
    3: _add_web_conversation_tables,
    4: _migrate_web_conversation_tenant_identity,
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
