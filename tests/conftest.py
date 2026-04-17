"""Shared test fixtures for Skyforge."""

from __future__ import annotations

import pytest

from skyforge.core.registry import ProviderRegistry


@pytest.fixture
def fresh_registry() -> ProviderRegistry:
    """Return a clean provider registry for isolated tests."""
    return ProviderRegistry()
