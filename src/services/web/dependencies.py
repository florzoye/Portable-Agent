from langgraph.graph.state import CompiledStateGraph

from src.agents.llms.initializer import LLMInitializer
from src.factories.agents_factory import AgentsFactory
from src.agents.prompts.system import AgentSystemPrompt
from src.factories.checkpointer_factory import get_checkpointer
from src.factories.tools_factory import get_tools


async def get_agent(session_id: str) -> CompiledStateGraph:
    """
    Creates an agent for a specific web session.
    CompiledStateGraph is stateless — dialog state is persisted in checkpointer.
    session_id is used as thread_id.
    """
    checkpointer = await get_checkpointer()
    tools = await get_tools()

    return await AgentsFactory(
        name="web-assistant",
        model=LLMInitializer.get_selected(),
        tools=tools,
        system_prompt=AgentSystemPrompt(),
        checkpointer=checkpointer,
        tg_id=session_id,  
    ).aget_agent()