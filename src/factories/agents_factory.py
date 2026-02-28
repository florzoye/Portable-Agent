from langchain_core.tools import BaseTool
from langgraph.checkpoint.base import BaseCheckpointSaver
from langchain_core.language_models import BaseChatModel
from langchain.agents.structured_output import ResponseFormat
from langgraph.graph.state import CompiledStateGraph

from deepagents import create_deep_agent
from deepagents.backends import FilesystemBackend
from src.agents.prompts.system import AgentSystemPrompt
from src.factories.middleware_factory import MiddlewareFactory

from utils.metaclasses import AgentsFactoryMeta


class AgentsFactory(metaclass=AgentsFactoryMeta):
    def __init__(
        self,
        name: str,
        model: BaseChatModel,
        *,
        system_prompt: AgentSystemPrompt,
        checkpointer: BaseCheckpointSaver,
        tools: list[BaseTool] | None = None,
        middleware: MiddlewareFactory | None = None,
        response_format: ResponseFormat | None = None,
        tg_id: int | str | None = None,
    ):
        self.name = name
        self.model = model
        self.tools = tools or []
        self.middleware = middleware
        self.system_prompt = system_prompt
        self.response_format = response_format
        self.tg_id = tg_id
        self.checkpointer = checkpointer

    def _get_memory_path(self) -> str:
        return f"/memory/users/{self.tg_id}/AGENTS.md"

    async def aget_agent(self) -> CompiledStateGraph:
        return create_deep_agent(
            name=self.name,
            model=self.model,
            tools=self.tools,
            middleware=self.middleware.get_middleware() if self.middleware else [],
            system_prompt=self.system_prompt.get_prompt(
                memory_path=self._get_memory_path(),
                tg_id=self.tg_id,
            ),
            response_format=self.response_format,
            backend=FilesystemBackend(root_dir="/storage", virtual_mode=False),
            memory=[self._get_memory_path()] if self.tg_id else None,
            checkpointer=self.checkpointer,
        )