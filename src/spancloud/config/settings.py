"""Application settings loaded from environment and config files."""

from __future__ import annotations

import functools
import os
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings


def _load_persisted_env_files() -> None:
    """Load persisted provider settings from ~/.config/spancloud/*.env into os.environ.

    Called once before Settings is constructed so that values saved by
    previous sessions (e.g. SPANCLOUD_AWS_PROFILE) are available to
    pydantic_settings when it reads environment variables.

    Explicit environment variables always win — we never overwrite a key
    that is already set in the environment.
    """
    config_dir = Path.home() / ".config" / "spancloud"
    if not config_dir.exists():
        return
    for env_file in sorted(config_dir.glob("*.env")):
        try:
            for raw in env_file.read_text().splitlines():
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                key = key.strip()
                val = val.strip()
                if key and key not in os.environ:
                    os.environ[key] = val
        except OSError:
            pass


class ProviderSettings(BaseSettings):
    """Per-provider toggle and region configuration."""

    enabled: bool = Field(default=True, description="Whether this provider is active")
    default_region: str = Field(default="", description="Default region for resource queries")


class AWSSettings(ProviderSettings):
    """AWS-specific settings."""

    model_config = {"env_prefix": "SPANCLOUD_AWS_"}

    default_region: str = Field(default="us-east-1")
    profile: str = Field(default="", description="AWS CLI profile name")


class GCPSettings(ProviderSettings):
    """GCP-specific settings."""

    model_config = {"env_prefix": "SPANCLOUD_GCP_"}

    default_region: str = Field(default="us-central1")
    project_id: str = Field(default="", description="GCP project ID")


class VultrSettings(ProviderSettings):
    """Vultr-specific settings."""

    model_config = {"env_prefix": "SPANCLOUD_VULTR_"}

    api_key: str = Field(default="", description="Vultr API key")


class DigitalOceanSettings(ProviderSettings):
    """DigitalOcean-specific settings."""

    model_config = {"env_prefix": "SPANCLOUD_DIGITALOCEAN_"}

    token: str = Field(default="", description="DigitalOcean Personal Access Token")


class AzureSettings(ProviderSettings):
    """Azure-specific settings."""

    model_config = {"env_prefix": "SPANCLOUD_AZURE_"}

    subscription_id: str = Field(default="", description="Azure subscription ID")
    tenant_id: str = Field(default="", description="Azure tenant ID (optional)")


class OCISettings(ProviderSettings):
    """Oracle Cloud Infrastructure settings."""

    model_config = {"env_prefix": "SPANCLOUD_OCI_"}

    config_file: str = Field(
        default="~/.oci/config", description="Path to OCI SDK config file"
    )
    profile: str = Field(default="DEFAULT", description="OCI config profile name")
    compartment_id: str = Field(
        default="", description="Default compartment OCID (uses tenancy root if blank)"
    )
    default_region: str = Field(default="us-ashburn-1")


class AlibabaSettings(ProviderSettings):
    """Alibaba Cloud settings."""

    model_config = {"env_prefix": "SPANCLOUD_ALIBABA_"}

    access_key_id: str = Field(default="", description="Alibaba AccessKey ID")
    access_key_secret: str = Field(default="", description="Alibaba AccessKey Secret")
    default_region: str = Field(default="us-west-1", description="Default region ID")


class Settings(BaseSettings):
    """Top-level Spancloud configuration.

    Settings are loaded from environment variables prefixed with SPANCLOUD_
    and from a config file at ~/.config/spancloud/config.env if it exists.
    """

    model_config = {"env_prefix": "SPANCLOUD_"}

    # General
    log_level: str = Field(default="INFO", description="Logging level")
    config_dir: Path = Field(
        default_factory=lambda: Path.home() / ".config" / "spancloud",
        description="Directory for Spancloud configuration files",
    )

    # Provider configs
    aws: AWSSettings = Field(default_factory=AWSSettings)
    gcp: GCPSettings = Field(default_factory=GCPSettings)
    vultr: VultrSettings = Field(default_factory=VultrSettings)
    digitalocean: DigitalOceanSettings = Field(default_factory=DigitalOceanSettings)
    azure: AzureSettings = Field(default_factory=AzureSettings)
    oci: OCISettings = Field(default_factory=OCISettings)
    alibaba: AlibabaSettings = Field(default_factory=AlibabaSettings)

    def ensure_config_dir(self) -> Path:
        """Create the config directory if it doesn't exist and return its path."""
        self.config_dir.mkdir(parents=True, exist_ok=True)
        return self.config_dir


@functools.cache
def get_settings() -> Settings:
    """Return the cached global settings instance.

    Loads persisted provider env files the first time so that values saved
    by previous auth sessions survive restarts.
    """
    _load_persisted_env_files()
    return Settings()
