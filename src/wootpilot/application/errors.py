"""Application-level exceptions shared across integration boundaries."""

from __future__ import annotations


class WootPilotError(Exception):
    """Base class for expected WootPilot application failures."""


class ExternalServiceError(WootPilotError):
    """Controlled failure raised for an external provider interaction.

    Integrations raise this family only after translating a known transport,
    provider, or response-contract problem. Unexpected application defects
    should escape as their original exception type.
    """

    def __init__(
        self,
        code: str,
        *,
        operation: str,
        retryable: bool,
        status_code: int | None = None,
    ) -> None:
        """Create a controlled external-service failure.

        Args:
            code: Stable application-facing error code for logging and persistence.
            operation: Integration operation that failed.
            retryable: Whether retrying the same operation may succeed.
            status_code: HTTP status code when the provider returned one.
        """

        super().__init__(code)
        self.code = code
        self.operation = operation
        self.retryable = retryable
        self.status_code = status_code


class ChatwootApiError(ExternalServiceError):
    """Base class for controlled Chatwoot API failures."""


class ChatwootTransportError(ChatwootApiError):
    """Chatwoot request failed before a valid HTTP response was available."""


class ChatwootResponseError(ChatwootApiError):
    """Chatwoot returned an error status or an unexpected response body."""


class ModelProviderError(ExternalServiceError):
    """Base class for controlled model provider failures."""


class ModelProviderTransportError(ModelProviderError):
    """Model provider call failed before a valid response was available."""


class ModelProviderResponseError(ModelProviderError):
    """Model provider returned unsupported or invalid structured data."""
