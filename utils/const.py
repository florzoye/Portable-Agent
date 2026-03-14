import os

SCOPES = ['https://www.googleapis.com/auth/calendar']

FASTAPI_CALENDAR_PORT = int(os.getenv("FASTAPI_CALENDAR_PORT", "8001"))
MCP_CALENDAR_PORT = int(os.getenv("MCP_CALENDAR_PORT", "8002"))

_FASTAPI_HOST = os.getenv("FASTAPI_CALENDAR_HOST", "localhost")
_MCP_HOST = os.getenv("MCP_CALENDAR_HOST", "localhost")

GOOGLE_CALENDAR_REDIRECT_URI = os.getenv(
    "GOOGLE_CALENDAR_REDIRECT_URI",
    f"http://localhost:{FASTAPI_CALENDAR_PORT}/calendar/oauth/callback"
)

GOOGLE_CALENDAR_URI = f"http://{_FASTAPI_HOST}:{FASTAPI_CALENDAR_PORT}"
MCP_CALENDAR_URL = f"http://{_MCP_HOST}:{MCP_CALENDAR_PORT}/sse"

MCP_REMINDERS_PORT = int(os.getenv("MCP_REMINDERS_PORT", "8003"))
_MCP_REMINDERS_HOST = os.getenv("MCP_REMINDERS_HOST", "localhost")
MCP_REMINDERS_URL = f"http://{_MCP_REMINDERS_HOST}:{MCP_REMINDERS_PORT}/sse"