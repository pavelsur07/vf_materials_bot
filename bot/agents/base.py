from abc import ABC, abstractmethod

from pydantic import BaseModel


class AgentResult(BaseModel):
    answer: str
    confidence: float = 0.0
    sources: list[str] = []


class BaseAgent(ABC):
    name: str

    @abstractmethod
    async def run(self, query: str, context: dict[str, str]) -> AgentResult:
        """Run the agent with a user query and optional context."""
        ...
