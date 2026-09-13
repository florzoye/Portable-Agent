import os

import uvicorn


if __name__ == "__main__":
    uvicorn.run(
        "src.services.monitoring.app:app",
        host="0.0.0.0",
        port=int(os.environ.get("MONITORING_PORT", "8010")),
    )
