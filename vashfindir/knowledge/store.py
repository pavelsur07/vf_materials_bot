from vashfindir.knowledge.base import KnowledgeStore


class InMemoryKnowledgeStore(KnowledgeStore):
    """In-memory knowledge store for local development and tests."""

    def __init__(self) -> None:
        self._documents: list[str] = []

    async def add(self, document: str, metadata: dict[str, str] | None = None) -> None:
        self._documents.append(document)

    async def search(self, query: str, top_k: int = 5) -> list[str]:
        query_lower = query.lower()
        return [doc for doc in self._documents if query_lower in doc.lower()][:top_k]
