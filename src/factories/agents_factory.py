from langchain_core.tools import BaseTool
from langchain_core.messages import SystemMessage
from langgraph.graph.state import CompiledStateGraph
from langchain_core.language_models import BaseChatModel
from langchain.agents.structured_output import ResponseFormat

from deepagents import create_deep_agent
from deepagents.backends.protocol import BACKEND_TYPES
from src.factories.middleware_factory import MiddlewareFactory

class AgentsFactory:
    def __init__(
        self,
        name: str,
        model: BaseChatModel,
        *,
        tools: list[BaseTool] | None = None,
        middleware: MiddlewareFactory | None = None,
        system_prompt: str | SystemMessage | None = None,
        response_format: ResponseFormat | None = None,
        backend: BACKEND_TYPES | None = None,
        tg_id: int | str | None = None,
    ):
        self.name = name
        self.model = model
        self.tools = tools or []
        self.middleware = middleware
        self.system_prompt = system_prompt
        self.response_format = response_format
        self.backend = backend
        self.tg_id = tg_id

    def _get_memory_path(self) -> str:
        return f"/memory/users/{self.tg_id}/AGENTS.md"

    def _build_system_prompt(self) -> str | SystemMessage | None:
        if self.tg_id is None:
            return self.system_prompt

        memory_note = (
            f"\nYour memory file is located at: {self._get_memory_path()}"
            "\nAlways save information to this exact path."
        )

        if self.system_prompt is None:
            return memory_note
        if isinstance(self.system_prompt, str):
            return self.system_prompt + memory_note
        return SystemMessage(content=self.system_prompt.content + memory_note)

    async def aget_agent(self) -> CompiledStateGraph:
        return create_deep_agent(
            name=self.name,
            model=self.model,
            tools=self.tools,
            middleware=self.middleware.get_middleware() if self.middleware else [],
            system_prompt=self._build_system_prompt(),
            response_format=self.response_format,
            backend=self.backend,
            memory=[self._get_memory_path()] if self.tg_id else None,
        )