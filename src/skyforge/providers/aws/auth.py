"""AWS authentication using the native credential chain.

Supports runtime profile switching for multi-account access.
"""

from __future__ import annotations

import asyncio
import configparser
from pathlib import Path

import boto3
from botocore.exceptions import BotoCoreError, ClientError, NoCredentialsError

from skyforge.config import get_settings
from skyforge.utils.logging import get_logger

logger = get_logger(__name__)

AWS_CREDENTIALS_PATH = Path.home() / ".aws" / "credentials"
AWS_CONFIG_PATH = Path.home() / ".aws" / "config"


class AWSAuth:
    """Manages AWS authentication via the standard credential chain.

    Supports: environment variables, ~/.aws/credentials, IAM roles,
    SSO profiles, instance metadata, and runtime profile switching.
    """

    def __init__(self) -> None:
        self._session: boto3.Session | None = None
        self._active_profile: str = ""

    @property
    def active_profile(self) -> str:
        """Return the name of the currently active AWS profile."""
        return self._active_profile or "(default)"

    @property
    def session(self) -> boto3.Session:
        """Return the current boto3 session, creating one if needed."""
        if self._session is None:
            settings = get_settings().aws
            kwargs: dict[str, str] = {}
            profile = self._active_profile or settings.profile
            if profile:
                kwargs["profile_name"] = profile
            if settings.default_region:
                kwargs["region_name"] = settings.default_region
            self._session = boto3.Session(**kwargs)
        return self._session

    def set_profile(self, profile_name: str) -> None:
        """Switch to a different AWS profile at runtime.

        Invalidates the cached session so the next API call
        uses the new profile's credentials.

        Args:
            profile_name: AWS CLI profile name to switch to.
        """
        logger.info("Switching AWS profile to '%s'", profile_name)
        self._active_profile = profile_name
        self._session = None  # Force re-creation on next access

    # Profile type priority when falling back — SSO tends to be "newer + fresh
    # tokens", access_keys are long-lived, assume_role needs a working source.
    _PROFILE_FALLBACK_ORDER = {
        "sso": 0,
        "access_keys": 1,
        "assume_role": 2,
        "config": 3,
    }

    async def verify(self) -> bool:
        """Verify that credentials are valid by calling STS GetCallerIdentity.

        If the current profile has no credentials, iterates every configured
        profile — SSO first, then access-key profiles from ~/.aws/credentials,
        then assume-role profiles — until one works. Only falls back when no
        explicit profile was asked for (don't silently swap profiles on
        someone who passed --profile).

        Returns:
            True if credentials are valid and usable.
        """
        try:
            sts = self.session.client("sts")
            identity = await asyncio.to_thread(sts.get_caller_identity)
            logger.info(
                "AWS authenticated as %s (account %s, profile: %s)",
                identity.get("Arn", "unknown"),
                identity.get("Account", "unknown"),
                self.active_profile,
            )
            return True
        except (NoCredentialsError, ClientError, BotoCoreError) as exc:
            logger.debug(
                "Default auth failed (%s), trying configured profiles...", exc
            )

        # Fallback: walk every configured profile if no explicit profile was set
        if not self._active_profile:
            profiles = self.list_configured_profiles()
            profiles.sort(
                key=lambda p: self._PROFILE_FALLBACK_ORDER.get(
                    p.get("type", "config"), 9
                )
            )

            for prof in profiles:
                try:
                    self.set_profile(prof["name"])
                    sts = self.session.client("sts")
                    identity = await asyncio.to_thread(sts.get_caller_identity)
                    logger.info(
                        "AWS authenticated via profile '%s' (type=%s, account %s)",
                        prof["name"],
                        prof.get("type", "?"),
                        identity.get("Account", "unknown"),
                    )
                    return True
                except (NoCredentialsError, ClientError, BotoCoreError):
                    continue

            # Reset if nothing worked — don't leave the last-tried profile set
            self._active_profile = ""
            self._session = None

        logger.warning("AWS authentication failed: no valid credentials found")
        return False

    async def get_identity(self) -> dict[str, str]:
        """Return details about the authenticated AWS identity."""
        try:
            sts = self.session.client("sts")
            identity = await asyncio.to_thread(sts.get_caller_identity)
            return {
                "account": identity.get("Account", "unknown"),
                "arn": identity.get("Arn", "unknown"),
                "user_id": identity.get("UserId", "unknown"),
                "profile": self.active_profile,
            }
        except (NoCredentialsError, ClientError, BotoCoreError):
            return {
                "account": "unknown",
                "arn": "unknown",
                "user_id": "unknown",
                "profile": self.active_profile,
            }

    def client(self, service: str, region: str | None = None) -> object:
        """Create a boto3 client for the given service.

        Args:
            service: AWS service name (e.g., 'ec2', 's3').
            region: Optional region override.

        Returns:
            A boto3 service client.
        """
        kwargs: dict[str, str] = {}
        if region:
            kwargs["region_name"] = region
        return self.session.client(service, **kwargs)

    @staticmethod
    def list_configured_profiles() -> list[dict[str, str]]:
        """List all configured AWS profiles with their type (SSO, keys, role).

        Returns:
            List of dicts with 'name', 'type', 'region', 'account' (if known).
        """
        profiles: dict[str, dict[str, str]] = {}

        # Read credentials file
        if AWS_CREDENTIALS_PATH.exists():
            cred = configparser.ConfigParser()
            cred.read(AWS_CREDENTIALS_PATH)
            for section in cred.sections():
                name = section
                profiles[name] = {
                    "name": name,
                    "type": "access_keys",
                    "region": "",
                    "source": "credentials",
                }

        # Read config file (richer info)
        if AWS_CONFIG_PATH.exists():
            cfg = configparser.ConfigParser()
            cfg.read(AWS_CONFIG_PATH)
            for section in cfg.sections():
                # Skip sso-session blocks — they're session configs, not profiles
                if section.startswith("sso-session"):
                    continue

                name = section.removeprefix("profile ").strip()
                existing = profiles.get(name, {"name": name, "source": "config"})

                if "sso_start_url" in cfg[section] or "sso_session" in cfg[section]:
                    existing["type"] = "sso"
                    existing["sso_account"] = cfg[section].get(
                        "sso_account_id", ""
                    )
                elif "role_arn" in cfg[section]:
                    existing["type"] = "assume_role"
                    existing["role_arn"] = cfg[section].get("role_arn", "")
                    existing["source_profile"] = cfg[section].get(
                        "source_profile", ""
                    )
                elif name not in profiles:
                    existing["type"] = "config"

                existing["region"] = cfg[section].get(
                    "region", existing.get("region", "")
                )
                profiles[name] = existing

        return sorted(profiles.values(), key=lambda p: p["name"])
