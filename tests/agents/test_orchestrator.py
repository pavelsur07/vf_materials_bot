import pytest

from bot.agents.base import AgentResult, BaseAgent
from bot.agents.orchestrator import AgentOrchestrator
from bot.agents.registry import AgentRegistry


class DummyAgent(BaseAgent):
    name = "dummy"

    async def run(self, query: str, context: dict[str, str]) -> AgentResult:
        return AgentResult(answer=f"dummy: {query}")


class OtherAgent(BaseAgent):
    name = "other"

    async def run(self, query: str, context: dict[str, str]) -> AgentResult:
        return AgentResult(answer=f"other: {query}")


@pytest.fixture
def orchestrator() -> AgentOrchestrator:
    registry = AgentRegistry()
    registry.register(DummyAgent())
    registry.register(OtherAgent())
    return AgentOrchestrator(registry)


async def test_run_single(orchestrator: AgentOrchestrator) -> None:
    result = await orchestrator.run_single("dummy", "hello", {})
    assert result.answer == "dummy: hello"


async def test_run_parallel(orchestrator: AgentOrchestrator) -> None:
    results = await orchestrator.run_parallel(["dummy", "other"], "hello", {})
    assert results["dummy"].answer == "dummy: hello"
    assert results["other"].answer == "other: hello"
