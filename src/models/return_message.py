from data import get_config

async def status(message: str) -> dict[str]:
    return {'status': message}

async def health_check_message(database) -> dict:
    return {
        "status": "healthy",
        "database": database.db_type,
        "database_initialized": database.is_initialized,
        "config_initialized": get_config().is_initialized
    }
