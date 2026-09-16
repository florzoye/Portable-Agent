import uvicorn
from src.services.base import create_app
from src.services.calendar.server.google_calendar_api import router
from src.services.calendar.server.dependencies import configure_dependencies
from utils.const import FASTAPI_CALENDAR_PORT
from db.database import global_db_manager

configure_dependencies(global_db_manager)

app = create_app(
    title="Google Calendar Service",
    routers=[router],
    internal_auth=True,
    database_bootstrap=global_db_manager.create_tables,
)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=FASTAPI_CALENDAR_PORT, log_config=None)