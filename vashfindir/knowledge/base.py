from abc import ABC, abstractmethod


class KnowledgeStore(ABC):
    """Abstract storage for documents used by RAG/AI agents."""

    @abstractmethod
    async def add(self, document: str, metadata: dict[str, str] | None = None) -> None:
        """Add a document to the store."""
        ...

    @abstractmethod
    async def search(self, query: str, top_k: int = 5) -> list[str]:
        """Return top-k relevant documents for the query."""
        ...
