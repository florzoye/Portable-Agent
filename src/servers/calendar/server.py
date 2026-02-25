import uvicorn
from src.servers.base import create_app
from src.servers.calendar.google_calendar_api import router
from utils.const import FASTAPI_CALENDAR_PORT

app = create_app(title="Google Calendar Service", routers=[router])

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=FASTAPI_CALENDAR_PORT)