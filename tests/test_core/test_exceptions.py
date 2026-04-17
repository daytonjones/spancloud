"""Tests for custom exceptions."""

from __future__ import annotations

from skyforge.core.exceptions import (
    AuthenticationError,
    ProviderError,
    ProviderNotImplementedError,
    ResourceNotFoundError,
    SkyforgeError,
)


class TestExceptions:
    """Tests for the exception hierarchy."""

    def test_skyforge_error_is_base(self) -> None:
        assert issubclass(ProviderError, SkyforgeError)
        assert issubclass(AuthenticationError, ProviderError)
        assert issubclass(ResourceNotFoundError, ProviderError)
        assert issubclass(ProviderNotImplementedError, SkyforgeError)

    def test_provider_error_includes_provider_name(self) -> None:
        err = ProviderError("aws", "something broke")
        assert "aws" in str(err)
        assert "something broke" in str(err)
        assert err.provider == "aws"

    def test_auth_error_default_message(self) -> None:
        err = AuthenticationError("gcp")
        assert "gcp" in str(err)
        assert "Authentication failed" in str(err)

    def test_resource_not_found(self) -> None:
        err = ResourceNotFoundError("aws", "compute", "i-12345")
        assert "i-12345" in str(err)
        assert err.resource_type == "compute"
        assert err.resource_id == "i-12345"

    def test_provider_not_implemented(self) -> None:
        err = ProviderNotImplementedError("azure")
        assert "azure" in str(err)
        assert "not yet implemented" in str(err)
