"""Provider registry for dynamic provider discovery and access."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from skyforge.core.provider import BaseProvider


class ProviderRegistry:
    """Central registry that maps provider names to their implementations.

    Providers register themselves on import. The CLI and TUI layers use the
    registry to discover available providers at runtime.
    """

    def __init__(self) -> None:
        self._providers: dict[str, BaseProvider] = {}

    def register(self, provider: BaseProvider) -> None:
        """Register a provider instance.

        Args:
            provider: The provider to register.

        Raises:
            ValueError: If a provider with the same name is already registered.
        """
        if provider.name in self._providers:
            raise ValueError(
                f"Provider '{provider.name}' is already registered. "
                "Each provider name must be unique."
            )
        self._providers[provider.name] = provider

    def get(self, name: str) -> BaseProvider | None:
        """Look up a provider by name.

        Args:
            name: The short identifier (e.g., 'aws').

        Returns:
            The provider instance, or None if not found.
        """
        return self._providers.get(name)

    def list_providers(self) -> list[BaseProvider]:
        """Return all registered providers, sorted by name."""
        return sorted(self._providers.values(), key=lambda p: p.name)

    @property
    def provider_names(self) -> list[str]:
        """Return sorted list of registered provider names."""
        return sorted(self._providers.keys())

    def __contains__(self, name: str) -> bool:
        return name in self._providers

    def __len__(self) -> int:
        return len(self._providers)


# Global singleton — providers register against this instance.
registry = ProviderRegistry()
