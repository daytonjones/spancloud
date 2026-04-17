"""GCP authentication using the native Application Default Credentials chain."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import google.auth
from google.auth.exceptions import DefaultCredentialsError

from skyforge.config import get_settings
from skyforge.utils.logging import get_logger

if TYPE_CHECKING:
    from google.auth.credentials import Credentials

logger = get_logger(__name__)


class GCPAuth:
    """Manages GCP authentication via Application Default Credentials.

    Supports: gcloud auth application-default login, service account keys,
    workload identity, and metadata server (on GCE/GKE).
    """

    def __init__(self) -> None:
        self._credentials: Credentials | None = None
        self._project_id: str = ""

    @property
    def credentials(self) -> Credentials | None:
        """Return the current GCP credentials."""
        return self._credentials

    @property
    def project_id(self) -> str:
        """Return the active GCP project ID."""
        return self._project_id

    async def verify(self) -> bool:
        """Verify that Application Default Credentials are available.

        Returns:
            True if credentials were found and are usable.
        """
        try:
            credentials, project = await asyncio.to_thread(google.auth.default)
            self._credentials = credentials
            # Prefer explicit project from settings, fall back to ADC project.
            settings = get_settings().gcp
            self._project_id = settings.project_id or project or ""

            if not self._project_id:
                logger.warning(
                    "GCP credentials found but no project ID configured. "
                    "Set SKYFORGE_GCP_PROJECT_ID or run 'gcloud config set project <id>'."
                )

            logger.info("GCP authenticated for project '%s'", self._project_id)
            return True
        except DefaultCredentialsError:
            logger.warning(
                "GCP authentication failed. 'gcloud auth login' alone is not enough — "
                "the Python SDK requires Application Default Credentials. Run:\n"
                "  gcloud auth application-default login\n"
                "Then optionally set a default project:\n"
                "  gcloud config set project PROJECT_ID\n"
                "Or set SKYFORGE_GCP_PROJECT_ID in your environment."
            )
            return False

    async def get_identity(self) -> dict[str, str]:
        """Return details about the authenticated GCP identity."""
        return {
            "project_id": self._project_id,
            "credential_type": type(self._credentials).__name__ if self._credentials else "none",
        }
