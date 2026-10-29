import pytest

from vashfindir.knowledge.store import InMemoryKnowledgeStore


@pytest.fixture
def store() -> InMemoryKnowledgeStore:
    return InMemoryKnowledgeStore()


async def test_add_and_search(store: InMemoryKnowledgeStore) -> None:
    await store.add("hello world")
    await store.add("goodbye world")
    results = await store.search("hello")
    assert results == ["hello world"]


async def test_search_top_k(store: InMemoryKnowledgeStore) -> None:
    await store.add("hello one")
    await store.add("hello two")
    await store.add("hello three")
    results = await store.search("hello", top_k=2)
    assert len(results) == 2
