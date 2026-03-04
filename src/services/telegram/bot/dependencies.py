from langgraph.graph.state import CompiledStateGraph

from src.agents.llms.initializer import LLMInitializer
from src.agents.tools.calendar import get_calendar_tools
from src.agents.prompts.system import AgentSystemPrompt
from src.factories.agents_factory import AgentsFactory
from src.factories.checkpointer_factory import get_checkpointer


async def get_agent(tg_id: int) -> CompiledStateGraph:
    """
    Dependency: создаёт агента для конкретного пользователя.

    CompiledStateGraph stateless — состояние диалога персистируется
    в AsyncPostgresSaver.
    """
    checkpointer = await get_checkpointer()

    return await AgentsFactory(
        name="tg-assistant",
        model=LLMInitializer.get_llms()[0],
        tools=await get_calendar_tools(),
        system_prompt=AgentSystemPrompt(),
        checkpointer=checkpointer,
        tg_id=tg_id,
    ).aget_agent()