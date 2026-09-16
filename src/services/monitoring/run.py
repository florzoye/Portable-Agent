import os

import uvicorn
from db.sqlalchemy.monitoring_crud import MonitoringORM
from src.services.monitoring.app import create_app


if __name__ == "__main__":
    repository = MonitoringORM(
        f"sqlite+aiosqlite:///{os.environ.get('MONITORING_DB_PATH', 'data/db/monitoring.db')}",
    )
    uvicorn.run(
        create_app(repository),
        host="0.0.0.0",
        port=int(os.environ.get("MONITORING_PORT", "8010")),
    )
