from typing import Any


class Container:
    """Simple dependency injection container.

    Registers dependencies by their type/interface and resolves them on demand.
    """

    def __init__(self) -> None:
        self._registry: dict[type, Any] = {}

    def register(self, interface: type, instance: Any) -> None:
        """Register an instance for the given interface."""
        self._registry[interface] = instance

    def resolve(self, interface: type) -> Any:
        """Resolve a previously registered instance."""
        try:
            return self._registry[interface]
        except KeyError as exc:
            raise RuntimeError(f"Dependency {interface.__name__} not registered") from exc
