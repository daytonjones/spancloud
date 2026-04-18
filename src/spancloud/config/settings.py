"""Application settings loaded from environment and config files."""

from __future__ import annotations

import functools
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings


class ProviderSettings(BaseSettings):
    """Per-provider toggle and region configuration."""

    enabled: bool = Field(default=True, description="Whether this provider is active")
    default_region: str = Field(default="", description="Default region for resource queries")


class AWSSettings(ProviderSettings):
    """AWS-specific settings."""

    model_config = {"env_prefix": "SKYFORGE_AWS_"}

    default_region: str = Field(default="us-east-1")
    profile: str = Field(default="", description="AWS CLI profile name")


class GCPSettings(ProviderSettings):
    """GCP-specific settings."""

    model_config = {"env_prefix": "SKYFORGE_GCP_"}

    default_region: str = Field(default="us-central1")
    project_id: str = Field(default="", description="GCP project ID")


class VultrSettings(ProviderSettings):
    """Vultr-specific settings."""

    model_config = {"env_prefix": "SKYFORGE_VULTR_"}

    api_key: str = Field(default="", description="Vultr API key")


class DigitalOceanSettings(ProviderSettings):
    """DigitalOcean-specific settings."""

    model_config = {"env_prefix": "SKYFORGE_DIGITALOCEAN_"}

    token: str = Field(default="", description="DigitalOcean Personal Access Token")


class AzureSettings(ProviderSettings):
    """Azure-specific settings."""

    model_config = {"env_prefix": "SKYFORGE_AZURE_"}

    subscription_id: str = Field(default="", description="Azure subscription ID")
    tenant_id: str = Field(default="", description="Azure tenant ID (optional)")


class OCISettings(ProviderSettings):
    """Oracle Cloud Infrastructure settings."""

    model_config = {"env_prefix": "SKYFORGE_OCI_"}

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

    model_config = {"env_prefix": "SKYFORGE_ALIBABA_"}

    access_key_id: str = Field(default="", description="Alibaba AccessKey ID")
    access_key_secret: str = Field(default="", description="Alibaba AccessKey Secret")
    default_region: str = Field(default="us-west-1", description="Default region ID")


class Settings(BaseSettings):
    """Top-level Skyforge configuration.

    Settings are loaded from environment variables prefixed with SKYFORGE_
    and from a config file at ~/.config/skyforge/config.env if it exists.
    """

    model_config = {"env_prefix": "SKYFORGE_"}

    # General
    log_level: str = Field(default="INFO", description="Logging level")
    config_dir: Path = Field(
        default_factory=lambda: Path.home() / ".config" / "skyforge",
        description="Directory for Skyforge configuration files",
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
    """Return the cached global settings instance."""
    return Settings()
