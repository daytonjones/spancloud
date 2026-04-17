"""Tests for the provider registry."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from skyforge.core.provider import BaseProvider
from skyforge.core.resource import Resource, ResourceType

if TYPE_CHECKING:
    from skyforge.core.registry import ProviderRegistry


class FakeProvider(BaseProvider):
    """Minimal provider for testing the registry."""

    @property
    def name(self) -> str:
        return "fake"

    @property
    def display_name(self) -> str:
        return "Fake Cloud"

    @property
    def supported_resource_types(self) -> list[ResourceType]:
        return [ResourceType.COMPUTE]

    async def authenticate(self) -> bool:
        return True

    async def is_authenticated(self) -> bool:
        return True

    async def list_resources(
        self,
        resource_type: ResourceType,
        region: str | None = None,
        tags: dict[str, str] | None = None,
    ) -> list[Resource]:
        return []

    async def get_resource(
        self, resource_type: ResourceType, resource_id: str, region: str | None = None
    ) -> Resource:
        return Resource(
            id=resource_id,
            name="fake-resource",
            resource_type=resource_type,
            provider="fake",
        )


class TestProviderRegistry:
    """Tests for ProviderRegistry."""

    def test_register_and_get(self, fresh_registry: ProviderRegistry) -> None:
        provider = FakeProvider()
        fresh_registry.register(provider)

        assert fresh_registry.get("fake") is provider
        assert "fake" in fresh_registry
        assert len(fresh_registry) == 1

    def test_get_unknown_returns_none(self, fresh_registry: ProviderRegistry) -> None:
        assert fresh_registry.get("nonexistent") is None

    def test_duplicate_registration_raises(self, fresh_registry: ProviderRegistry) -> None:
        provider = FakeProvider()
        fresh_registry.register(provider)

        with pytest.raises(ValueError, match="already registered"):
            fresh_registry.register(FakeProvider())

    def test_list_providers_sorted(self, fresh_registry: ProviderRegistry) -> None:
        # Register in reverse order to verify sorting.
        class ZProvider(FakeProvider):
            @property
            def name(self) -> str:
                return "zzz"

        class AProvider(FakeProvider):
            @property
            def name(self) -> str:
                return "aaa"

        fresh_registry.register(ZProvider())
        fresh_registry.register(AProvider())

        names = [p.name for p in fresh_registry.list_providers()]
        assert names == ["aaa", "zzz"]

    def test_provider_names(self, fresh_registry: ProviderRegistry) -> None:
        fresh_registry.register(FakeProvider())
        assert fresh_registry.provider_names == ["fake"]
