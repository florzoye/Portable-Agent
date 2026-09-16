import argparse
import asyncio

from data import init
from db.sqlalchemy.migrations import check_database, migrate_database
from db.sqlalchemy.models import Base
from db.sqlalchemy.session import sqlalchemy_manager


async def main(command: str) -> int:
    init()
    sqlalchemy_manager.init()
    engine = sqlalchemy_manager.get_engine()
    if command == "check":
        status = await check_database(engine)
        print(
            f"current={status.current_version} target={status.target_version} "
            f"upgrade_required={status.upgrade_required}"
        )
        return 0
    await migrate_database(
        engine,
        Base.metadata,
        extra_tables=("users", "google_tokens", "model_profiles"),
    )
    return 0


def cli() -> None:
    parser = argparse.ArgumentParser(description="Manage database schema")
    parser.add_argument("command", choices=("check", "upgrade"))
    args = parser.parse_args()
    raise SystemExit(asyncio.run(main(args.command)))


if __name__ == "__main__":
    cli()
