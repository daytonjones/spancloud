"""Oracle Cloud Infrastructure authentication.

OCI uses a config file at ~/.oci/config (like ~/.aws/credentials) plus
an API-signing key pair. Profiles let a user swap between tenancies.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any

from skyforge.config import get_settings
from skyforge.utils.logging import get_logger

logger = get_logger(__name__)


class OCIAuth:
    """Manages OCI config + signer."""

    def __init__(self) -> None:
        self._config: dict[str, Any] = {}
        self._profile: str = ""
        self._config_file: str = ""
        self._compartment_id: str = ""
        self._region: str = ""
        self._tenancy_name: str = ""
        self._user_email: str = ""

    @property
    def profile(self) -> str:
        return self._profile

    @property
    def config(self) -> dict[str, Any]:
        return self._config

    @property
    def compartment_id(self) -> str:
        """Compartment OCID — falls back to the tenancy root."""
        return self._compartment_id or self._config.get("tenancy", "")

    @property
    def region(self) -> str:
        return self._region or self._config.get("region", "")

    def set_profile(self, profile: str) -> None:
        """Switch to a different profile; invalidates cached config."""
        self._profile = profile
        self._config = {}

    def _ensure_loaded(self) -> None:
        """Populate self._config from the OCI config file."""
        if self._config:
            return
        settings = get_settings().oci
        self._config_file = os.path.expanduser(settings.config_file)
        self._profile = self._profile or settings.profile or "DEFAULT"
        self._compartment_id = self._compartment_id or settings.compartment_id

        import oci

        if not Path(self._config_file).exists():
            raise FileNotFoundError(
                f"OCI config not found at {self._config_file}. "
                "Run `oci setup config` to create one, or run "
                "`skyforge auth login oci`."
            )

        self._config = oci.config.from_file(
            file_location=self._config_file, profile_name=self._profile
        )
        oci.config.validate_config(self._config)
        self._region = self._config.get("region", settings.default_region)

    async def verify(self) -> bool:
        """Verify that OCI credentials and a reachable region work."""
        try:
            info = await asyncio.to_thread(self._sync_verify)
            self._tenancy_name = info.get("tenancy_name", "")
            self._user_email = info.get("user_email", "")
            logger.info(
                "OCI authenticated as '%s' in tenancy '%s' (region %s)",
                self._user_email or "unknown",
                self._tenancy_name or "unknown",
                self.region,
            )
            return True
        except Exception as exc:
            logger.warning("OCI authentication failed: %s", exc)
            return False

    def _sync_verify(self) -> dict[str, str]:
        """Load config, then resolve tenancy + user metadata."""
        import oci

        self._ensure_loaded()
        identity = oci.identity.IdentityClient(self._config)

        tenancy_ocid = self._config.get("tenancy", "")
        user_ocid = self._config.get("user", "")

        info: dict[str, str] = {}
        try:
            tenancy = identity.get_tenancy(tenancy_ocid).data
            info["tenancy_name"] = getattr(tenancy, "name", "") or ""
        except Exception:
            pass
        try:
            user = identity.get_user(user_ocid).data
            info["user_email"] = (
                getattr(user, "email", "") or getattr(user, "name", "") or ""
            )
        except Exception:
            pass
        return info

    async def get_identity(self) -> dict[str, str]:
        """Return the signed-in identity summary."""
        return {
            "profile": self._profile,
            "tenancy": self._config.get("tenancy", ""),
            "tenancy_name": self._tenancy_name,
            "user_email": self._user_email,
            "region": self.region,
            "compartment": self.compartment_id,
        }

    def list_profiles(self) -> list[str]:
        """Return the profile names defined in the OCI config file."""
        self._config_file = self._config_file or os.path.expanduser(
            get_settings().oci.config_file
        )
        path = Path(self._config_file)
        if not path.exists():
            return []

        profiles: list[str] = []
        for line in path.read_text().splitlines():
            line = line.strip()
            if line.startswith("[") and line.endswith("]"):
                profiles.append(line[1:-1])
        return profiles
