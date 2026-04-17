"""Tests for AWS multi-account profile support."""

from __future__ import annotations


class TestAWSAuthProfileSwitching:
    """Tests for runtime profile switching in AWSAuth."""

    def test_default_active_profile(self) -> None:
        from skyforge.providers.aws.auth import AWSAuth

        auth = AWSAuth()
        assert auth.active_profile == "(default)"

    def test_set_profile_changes_active(self) -> None:
        from skyforge.providers.aws.auth import AWSAuth

        auth = AWSAuth()
        auth.set_profile("production")
        assert auth.active_profile == "production"

    def test_set_profile_invalidates_session(self) -> None:
        from skyforge.providers.aws.auth import AWSAuth

        auth = AWSAuth()
        # Access session to cache it
        _ = auth.session
        assert auth._session is not None

        # Switch profile should invalidate
        auth.set_profile("staging")
        assert auth._session is None
        assert auth.active_profile == "staging"

    def test_set_profile_multiple_switches(self) -> None:
        from skyforge.providers.aws.auth import AWSAuth

        auth = AWSAuth()
        auth.set_profile("dev")
        assert auth.active_profile == "dev"
        auth.set_profile("prod")
        assert auth.active_profile == "prod"
        auth.set_profile("staging")
        assert auth.active_profile == "staging"

    def test_list_configured_profiles_returns_list(self) -> None:
        from skyforge.providers.aws.auth import AWSAuth

        # Should return a list (may be empty if no AWS config)
        profiles = AWSAuth.list_configured_profiles()
        assert isinstance(profiles, list)
