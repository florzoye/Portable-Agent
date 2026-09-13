import sys
import logging

def setup_logging(service_name: str = "portable-agent"):
    level = logging.getLevelName(
        __import__("os").environ.get("LOG_LEVEL", "INFO").upper()
    )
    if not isinstance(level, int):
        level = logging.INFO
    logging.basicConfig(
        level=level,
        format=f"%(asctime)s | {service_name} | %(levelname)s | %(name)s | %(message)s",
        datefmt="%H:%M:%S",
        handlers=[
            logging.StreamHandler(sys.stdout)  
        ],
        force=True,
    )
    for noisy_logger in ("httpx", "httpcore", "asyncio", "uvicorn.access"):
        logging.getLogger(noisy_logger).setLevel(logging.WARNING)
