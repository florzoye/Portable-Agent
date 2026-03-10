import logging
from psycopg_pool import AsyncConnectionPool
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.checkpoint.base import BaseCheckpointSaver

logger = logging.getLogger(__name__)

_checkpointer: AsyncPostgresSaver | None = None
_pool: AsyncConnectionPool | None = None


async def get_checkpointer() -> BaseCheckpointSaver:
    """
    Returns a singleton AsyncPostgresSaver based on a connection pool.
    Call once when the application starts (on_startup).
    """
    global _checkpointer, _pool

    if _checkpointer is not None:
        return _checkpointer

    from data.init_configs import get_config

    cfg = get_config()
    db = cfg.DB_CONFIG

    conn_string = (
        f"postgresql://{db.DB_USER}:{db.DB_PASSWORD}"
        f"@{db.DB_HOST}:{db.DB_PORT}/{db.DB_NAME}"
    )

    _pool = AsyncConnectionPool(
        conninfo=conn_string,
        max_size=10,
        kwargs={
            "autocommit": True,
            "prepare_threshold": 0,  
        },
        open=False,
    )
    await _pool.open()

    _checkpointer = AsyncPostgresSaver(_pool)

    await _checkpointer.setup()

    logger.info("✅ AsyncPostgresSaver initialized")
    return _checkpointer


async def close_checkpointer() -> None:
    global _checkpointer, _pool

    if _pool is not None:
        await _pool.close()
        _pool = None
        _checkpointer = None
        logger.info("✅ AsyncPostgresSaver is closed")