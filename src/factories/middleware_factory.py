from typing import List, Optional

from deepagents.backends.state import StateBackend
from deepagents.backends.protocol import BACKEND_TYPES
from langchain.agents.middleware.types import AgentMiddleware
from deepagents.middleware import SkillsMiddleware, MemoryMiddleware
from deepagents.middleware.patch_tool_calls import PatchToolCallsMiddleware
from deepagents.middleware.summarization import SummarizationMiddleware, ContextSize


class MiddlewareFactory:
    def __init__(self) -> None:
        self._middleware: List[AgentMiddleware] = []

    def add_skills(
        self,
        backend: Optional[BACKEND_TYPES] = None,
        sources: Optional[List[str]] = None,
    ) -> "MiddlewareFactory":
        backend_instance = backend if backend is not None else (lambda rt: StateBackend(rt))
        sources_list = sources or ["/skills/base/"]
        self._middleware.append(SkillsMiddleware(backend=backend_instance, sources=sources_list))
        return self

    def add_memory(
        self,
        backend: BACKEND_TYPES,
        sources: Optional[List[str]] = None,
    ) -> "MiddlewareFactory":
        self._middleware.append(MemoryMiddleware(backend=backend, sources=sources))
        return self

    def add_patch_tool_calls(self) -> "MiddlewareFactory":
        self._middleware.append(PatchToolCallsMiddleware())
        return self

    def add_summarization(
        self,
        model: str,
        backend: BACKEND_TYPES,
        trigger: ContextSize = ("fraction", 0.85),
        keep: ContextSize = ("fraction", 0.10),
    ) -> "MiddlewareFactory":
        self._middleware.append(
            SummarizationMiddleware(model=model, backend=backend, trigger=trigger, keep=keep)
        )
        return self

    def get_middleware(self) -> List[AgentMiddleware]:
        return self._middleware