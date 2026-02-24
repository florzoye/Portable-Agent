from data import get_config
ports_config = get_config().PORTS_CONFIG

SCOPES = ['https://www.googleapis.com/auth/calendar']
GOOGLE_CALENDAR_REDIRECT_URI = f'http://localhost:{ports_config.FASTAPI_CALENDAR_PORT}/calendar/oauth/callback'

GOOGLE_CALENDAR_URI = f'http://localhost:{ports_config.FASTAPI_CALENDAR_PORT}'
MCP_CALENDAR_URL = f"http://localhost:{ports_config.MCP_CALENDAR_PORT}/sse"