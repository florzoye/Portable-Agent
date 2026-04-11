import asyncio
import uvicorn
from loguru import logger
from langchain_core.language_models import BaseChatModel

from src.agents.llms.initializer import LLMInitializer
from utils.model_selector import select_model
from data import init, get_config

selected_llm: BaseChatModel | None = None


def get_selected_llm() -> BaseChatModel:
    if selected_llm is None:
        raise RuntimeError("Model not selected")
    return selected_llm


async def _init_llms() -> tuple:
    llms = await LLMInitializer.initialize()
    wrappers = LLMInitializer.get_wrappers()
    return wrappers, llms


async def _main():
    cfg = get_config()

    wrappers, llms = await _init_llms()
    selected = await select_model(wrappers, llms)
    LLMInitializer.set_selected(selected)

    host = getattr(cfg, "WEB_HOST", "0.0.0.0")
    port = getattr(cfg, "WEB_PORT", 8000)

    logger.info(f"🚀 Starting web assistant on http://{host}:{port}")

    config = uvicorn.Config(
        "src.services.web.app:app",
        host=host,
        port=port,
        log_level="info",
        # reload=True,  
    )
    server = uvicorn.Server(config)
    await server.serve()


if __name__ == "__main__":
    try:
        init()
        asyncio.run(_main())
    except KeyboardInterrupt:
        pass