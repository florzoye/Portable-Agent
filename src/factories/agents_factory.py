from src.factories.middleware_factory import MiddlewareFactory

from deepagents import create_deep_agent
from langchain_core.tools import BaseTool
from langchain.messages import SystemMessage
from langgraph.graph.state import CompiledStateGraph
from langchain_core.language_models import BaseChatModel
from langchain.agents.structured_output import ResponseFormat


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
    ):
        self.name = name
        self.model = model
        self.tools = tools or []
        self.middleware = middleware
        self.system_prompt = system_prompt
        self.response_format = response_format

    def get_agent(self) -> CompiledStateGraph: 
        return create_deep_agent(
            name=self.name,
            model=self.model,
            tools=self.tools,
            middleware=self.middleware.get_middleware() if self.middleware else [],
            system_prompt=self.system_prompt,
            response_format=self.response_format,
        )