from data import init
init()

from src.services.reminders.mcp.server import mcp

if __name__ == "__main__":
    mcp.run(transport="sse")