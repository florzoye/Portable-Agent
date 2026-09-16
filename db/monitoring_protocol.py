from abc import ABC, abstractmethod
from typing import Any


class MonitoringBase(ABC):
    @abstractmethod
    async def create_tables(self) -> None:
        ...

    @abstractmethod
    async def record(self, payload: dict[str, Any]) -> None:
        ...

    @abstractmethod
    async def stats(self) -> dict[str, Any]:
        ...
