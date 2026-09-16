import os

from db.sqlalchemy.monitoring_crud import MonitoringORM


_repositories: dict[str, MonitoringORM] = {}


def get_legacy_repository() -> MonitoringORM:
    """Compatibility repository for direct in-process callers.

    Production ASGI startup should construct and inject a repository via
    ``monitoring.run``.
    """
    path = os.environ.get("MONITORING_DB_PATH", "data/db/monitoring.db")
    if path not in _repositories:
        _repositories[path] = MonitoringORM(f"sqlite+aiosqlite:///{path}")
    return _repositories[path]
