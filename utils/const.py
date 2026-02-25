SCOPES = ['https://www.googleapis.com/auth/calendar']

FASTAPI_CALENDAR_PORT = 8001
MCP_CALENDAR_PORT = 8002

GOOGLE_CALENDAR_REDIRECT_URI = f'http://localhost:{FASTAPI_CALENDAR_PORT}/calendar/oauth/callback'

GOOGLE_CALENDAR_URI = f'http://localhost:{FASTAPI_CALENDAR_PORT}'

MCP_CALENDAR_URL = f'http://localhost:{MCP_CALENDAR_PORT}/sse'