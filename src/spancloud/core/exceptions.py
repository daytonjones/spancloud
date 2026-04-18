"""Custom exceptions for Spancloud."""


class SpancloudError(Exception):
    """Base exception for all Spancloud errors."""


class ProviderError(SpancloudError):
    """Error originating from a cloud provider interaction."""

    def __init__(self, provider: str, message: str) -> None:
        self.provider = provider
        super().__init__(f"[{provider}] {message}")


class AuthenticationError(ProviderError):
    """Failed to authenticate with a cloud provider."""

    def __init__(self, provider: str, message: str = "Authentication failed") -> None:
        super().__init__(provider, message)


class ResourceNotFoundError(ProviderError):
    """Requested resource does not exist."""

    def __init__(self, provider: str, resource_type: str, resource_id: str) -> None:
        self.resource_type = resource_type
        self.resource_id = resource_id
        super().__init__(provider, f"{resource_type} '{resource_id}' not found")


class ProviderNotImplementedError(SpancloudError):
    """Provider exists but is not yet implemented."""

    def __init__(self, provider: str) -> None:
        self.provider = provider
        super().__init__(
            f"Provider '{provider}' is registered but not yet implemented. "
            "Contributions welcome!"
        )
