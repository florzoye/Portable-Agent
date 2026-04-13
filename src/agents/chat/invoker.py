from loguru import logger
from langgraph.graph.state import CompiledStateGraph
from langchain_core.language_models import BaseChatModel

from src.agents.chat.base import StreamSender

class AgentInvoker:
    """
    Unified interface for invoking a LangGraph agent.

    - Detects whether the underlying LLM supports streaming.
    - If a sender is provided, delivers tokens as they are generated (e.g. WebSocket).
    - Falls back to a plain ainvoke call if streaming is unsupported or fails.
    - Always returns the full response text.
    """

    def __init__(self, agent: CompiledStateGraph, user_id: str | int):
        self.agent = agent
        self.user_id = str(user_id)

    @staticmethod
    def _supports_streaming(llm: BaseChatModel | None) -> bool:
        """
        Returns True if the LLM instance advertises streaming support.
        If llm is None, streaming is attempted unconditionally (with fallback on failure).
        """
        if llm is None:
            return True
        return getattr(llm, "streaming", False) or callable(getattr(llm, "stream", None))

    def _build_config(self, runnable_config: dict | None = None) -> dict:
        """Merges thread config with any extra runnable config."""
        base = {"configurable": {"thread_id": self.user_id}}
        if runnable_config:
            base.update(runnable_config)
        return base

    async def _stream_tokens(
        self,
        messages: list,
        config: dict,
        sender: StreamSender | None,
    ) -> tuple[str, bool]:
        """
        Streams tokens via astream_events and accumulates the full response.
        Forwards each token to the sender if one is provided.

        Returns:
            (full_text, success) — on failure returns ("", False) for fallback.
        """
        full_text = ""
        try:
            async for event in self.agent.astream_events(
                {"messages": messages},
                config=config,
                version="v2",
            ):
                if event.get("event") != "on_chat_model_stream":
                    continue

                chunk = event["data"]["chunk"]
                token: str = chunk.content if hasattr(chunk, "content") else str(chunk)
                if not token:
                    continue

                full_text += token
                if sender is not None:
                    await sender.send_chunk(token)

            if sender is not None:
                await sender.send_done()

            return full_text, True

        except Exception as e:
            logger.warning(
                f"Streaming failed for user={self.user_id}, falling back to ainvoke: {e}"
            )
            return "", False

    async def _invoke_plain(self, messages: list, config: dict) -> str:
        """Invokes the agent without streaming and returns the final message content."""
        result = await self.agent.ainvoke({"messages": messages}, config=config)
        return result["messages"][-1].content

    async def invoke(
        self,
        user_message: str,
        runnable_config: dict | None = None,
        *,
        llm: BaseChatModel | None = None,
        sender: StreamSender | None = None,
    ) -> str:
        """
        Main entry point for agent invocation.

        Args:
            user_message:    The user's input text.
            runnable_config: Extra config merged into the agent call (e.g. cfg.RUNNABLE_CONFIG).
            llm:             LLM instance used to check streaming support.
                             If None, streaming is always attempted.
            sender:          StreamSender implementation for token-by-token delivery.
                             If None, streaming runs silently (no chunks are forwarded).

        Returns:
            The full response text from the agent.
        """
        messages = [{"role": "user", "content": user_message}]
        config = self._build_config(runnable_config)

        if self._supports_streaming(llm):
            text, ok = await self._stream_tokens(messages, config, sender)
            if ok:
                return text
            logger.info(f"Fallback to plain invoke for user={self.user_id}")

        return await self._invoke_plain(messages, config)