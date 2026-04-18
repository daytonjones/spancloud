"""Tests for AWS multi-account profile support."""

from __future__ import annotations


class TestAWSAuthProfileSwitching:
    """Tests for runtime profile switching in AWSAuth."""

    def test_default_active_profile(self) -> None:
        from spancloud.providers.aws.auth import AWSAuth

        auth = AWSAuth()
        assert auth.active_profile == "(default)"

    def test_set_profile_changes_active(self) -> None:
        from spancloud.providers.aws.auth import AWSAuth

        auth = AWSAuth()
        auth.set_profile("production")
        assert auth.active_profile == "production"

    def test_set_profile_invalidates_session(self) -> None:
        from spancloud.providers.aws.auth import AWSAuth

        auth = AWSAuth()
        # Access session to cache it
        _ = auth.session
        assert auth._session is not None

        # Switch profile should invalidate
        auth.set_profile("staging")
        assert auth._session is None
        assert auth.active_profile == "staging"

    def test_set_profile_multiple_switches(self) -> None:
        from spancloud.providers.aws.auth import AWSAuth

        auth = AWSAuth()
        auth.set_profile("dev")
        assert auth.active_profile == "dev"
        auth.set_profile("prod")
        assert auth.active_profile == "prod"
        auth.set_profile("staging")
        assert auth.active_profile == "staging"

    def test_list_configured_profiles_returns_list(self) -> None:
        from spancloud.providers.aws.auth import AWSAuth

        # Should return a list (may be empty if no AWS config)
        profiles = AWSAuth.list_configured_profiles()
        assert isinstance(profiles, list)

    async def test_verify_falls_back_to_access_key_profile(self) -> None:
        """verify() must try access-key profiles, not just SSO, as a fallback.

        Regression: the original implementation only looped over SSO
        profiles when the default chain failed, which left access-key
        users unauthenticated.
        """
        from unittest.mock import MagicMock, patch

        from botocore.exceptions import NoCredentialsError

        from spancloud.providers.aws.auth import AWSAuth

        auth = AWSAuth()
        # No explicit profile so the fallback branch is active.

        # First STS call (default chain) fails; then we try 'dev' (access_keys)
        # which also fails; finally 'prod' (access_keys) succeeds.
        call_count = {"i": 0}

        def fake_get_caller_identity():
            call_count["i"] += 1
            if call_count["i"] == 1:
                raise NoCredentialsError()
            if call_count["i"] == 2:
                raise NoCredentialsError()
            return {"Arn": "arn:aws:iam::111:user/me", "Account": "111"}

        fake_sts = MagicMock()
        fake_sts.get_caller_identity.side_effect = fake_get_caller_identity
        fake_session = MagicMock()
        fake_session.client.return_value = fake_sts

        profiles = [
            {"name": "dev", "type": "access_keys", "region": ""},
            {"name": "prod", "type": "access_keys", "region": ""},
        ]

        with (
            patch.object(AWSAuth, "session", new=fake_session),
            patch.object(AWSAuth, "list_configured_profiles", return_value=profiles),
        ):
            result = await auth.verify()

        assert result is True
        assert auth.active_profile == "prod"

    async def test_verify_resets_profile_when_nothing_works(self) -> None:
        """If every fallback profile fails, we must not leave one pinned."""
        from unittest.mock import MagicMock, patch

        from botocore.exceptions import NoCredentialsError

        from spancloud.providers.aws.auth import AWSAuth

        auth = AWSAuth()

        fake_sts = MagicMock()
        fake_sts.get_caller_identity.side_effect = NoCredentialsError()
        fake_session = MagicMock()
        fake_session.client.return_value = fake_sts

        profiles = [
            {"name": "dev", "type": "access_keys", "region": ""},
            {"name": "prod", "type": "sso", "region": ""},
        ]

        with (
            patch.object(AWSAuth, "session", new=fake_session),
            patch.object(AWSAuth, "list_configured_profiles", return_value=profiles),
        ):
            result = await auth.verify()

        assert result is False
        # Must NOT leave 'prod' or 'dev' pinned if nothing worked
        assert auth._active_profile == ""
