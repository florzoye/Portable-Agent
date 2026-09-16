from langgraph.graph.state import CompiledStateGraph
from langchain_core.language_models import BaseChatModel

from src.agents.llms.initializer import LLMInitializer
from src.factories.agents_factory import AgentsFactory
from src.agents.prompts.system import AgentSystemPrompt
from src.factories.checkpointer_factory import get_checkpointer
from src.factories.tools_factory import get_tools
from db.database import global_db_manager
from src.agents.providers.factory import UserModelFactory
from src.services.model_profiles import ModelProfileApplication

_session_models: dict[str, BaseChatModel] = {}
_model_profiles = ModelProfileApplication(global_db_manager)


def get_model_profiles() -> ModelProfileApplication:
    return _model_profiles


def set_session_model(
    session_id: str,
    llm: BaseChatModel,
    user_id: int | None = None,
) -> None:
    _session_models[session_id] = llm
    AgentsFactory.reset(tg_id=user_id if user_id is not None else session_id)


def clear_session_model(session_id: str) -> None:
    _session_models.pop(session_id, None)


def get_session_model(session_id: str) -> BaseChatModel:
    return _session_models.get(session_id) or LLMInitializer.get_selected()


async def get_user_model(user_id: int) -> BaseChatModel | None:
    async with global_db_manager.transaction() as session:
        profiles = global_db_manager.get_model_profiles_repo(session)
        return await UserModelFactory(profiles).create_active(user_id)


async def get_agent(session_id: str, user_id: int | None = None) -> CompiledStateGraph:
    """
    Creates an agent for a specific web session.
    CompiledStateGraph is stateless — dialog state is persisted in checkpointer.
    session_id is used as thread_id.
    """
    checkpointer = await get_checkpointer()
    tools = await get_tools()

    user_model = await get_user_model(user_id) if user_id is not None else None
    return await AgentsFactory(
        name="web-assistant",
        model=user_model or get_session_model(session_id),
        tools=tools,
        system_prompt=AgentSystemPrompt(),
        checkpointer=checkpointer,
        tg_id=user_id if user_id is not None else session_id,
        channel='web'
    ).aget_agent()