from langgraph.graph.state import CompiledStateGraph

from src.agents.llms.initializer import LLMInitializer
from src.factories.agents_factory import AgentsFactory
from src.agents.prompts.system import AgentSystemPrompt
from src.factories.checkpointer_factory import get_checkpointer

from src.factories.tools_factory import get_tools

async def get_agent(tg_id: int) -> CompiledStateGraph:
    """
    Dependency: creates an agent for a specific user.

    CompiledStateGraph stateless — the dialog state is persisted
    in AsyncPostgresSaver.
    """
    return await AgentsFactory(
        name="tg-assistant",
        model=LLMInitializer.get_selected(),
        tools=await get_tools(),
        system_prompt=AgentSystemPrompt(),
        checkpointer=await get_checkpointer(),
        tg_id=tg_id,
    ).aget_agent()