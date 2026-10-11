class BotError(Exception):
    """Base exception for the project."""


class AgentError(BotError):
    """Raised when an AI agent fails."""


class IntegrationError(BotError):
    """Raised when an external integration fails."""


class KnowledgeBaseError(BotError):
    """Raised when the knowledge base operation fails."""


class UseCaseError(BotError):
    """Raised when a use case scenario cannot be completed."""
