import uvicorn
from src.servers.base import create_app
from src.servers.calendar.google_calendar_api import router

app = create_app(title="Google Calendar Service", routers=[router])

if __name__ == "__main__":
    from data import get_config
    ports_config = get_config().PORTS_CONFIG
    uvicorn.run(app, host="0.0.0.0", port=ports_config.FASTAPI_CALENDAR_PORT)