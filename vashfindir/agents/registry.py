from vashfindir.agents.base import BaseAgent


class AgentRegistry:
    """Keeps registered agents and resolves them by name."""

    def __init__(self) -> None:
        self._agents: dict[str, BaseAgent] = {}

    def register(self, agent: BaseAgent) -> None:
        self._agents[agent.name] = agent

    def get(self, name: str) -> BaseAgent:
        try:
            return self._agents[name]
        except KeyError as exc:
            raise RuntimeError(f"Agent {name} not registered") from exc

    def list_names(self) -> list[str]:
        return list(self._agents.keys())
