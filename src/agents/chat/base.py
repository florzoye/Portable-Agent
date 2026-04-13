from abc import ABC, abstractmethod

class StreamSender(ABC):
    """
    Abstract base class for streaming chunk delivery.
    Implement this for each transport layer (WebSocket, Telegram, etc.).
    """
    @abstractmethod
    async def send_chunk(self, chunk: str) -> None:
        """Send a single generated token/chunk to the client."""
        ...

    @abstractmethod
    async def send_done(self) -> None:
        """Signal that streaming has completed."""
        ...

