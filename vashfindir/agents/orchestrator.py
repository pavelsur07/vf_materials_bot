import asyncio

from vashfindir.agents.base import AgentResult
from vashfindir.agents.registry import AgentRegistry


class AgentOrchestrator:
    """Coordinates one or more agents for a given request."""

    def __init__(self, registry: AgentRegistry) -> None:
        self._registry = registry

    async def run_single(self, name: str, query: str, context: dict[str, str]) -> AgentResult:
        agent = self._registry.get(name)
        return await agent.run(query, context)

    async def run_parallel(
        self,
        names: list[str],
        query: str,
        context: dict[str, str],
    ) -> dict[str, AgentResult]:
        agents = [self._registry.get(name) for name in names]
        results = await asyncio.gather(*(agent.run(query, context) for agent in agents))
        return dict(zip(names, results, strict=True))
