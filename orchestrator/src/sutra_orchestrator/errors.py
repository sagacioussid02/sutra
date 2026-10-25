"""Exceptions raised by the orchestrator at startup."""


class OrchestratorError(Exception):
    """Base class for orchestrator errors."""


class ConfigError(OrchestratorError):
    """Required configuration is missing or invalid."""


class GatewayAuthError(OrchestratorError):
    """The gateway rejected the connection, almost always a bad bearer token."""


class GatewayUnreachableError(OrchestratorError):
    """The gateway could not be reached at all."""
