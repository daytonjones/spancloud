"""GCP authentication using the native Application Default Credentials chain."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import google.auth
from google.auth.exceptions import DefaultCredentialsError

from spancloud.config import get_settings
from spancloud.utils.logging import get_logger

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
                    "Set SPANCLOUD_GCP_PROJECT_ID or run 'gcloud config set project <id>'."
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
                "Or set SPANCLOUD_GCP_PROJECT_ID in your environment."
            )
            return False

    def set_project(self, project_id: str) -> None:
        """Switch the active GCP project for subsequent calls.

        Does not invalidate credentials (ADC credentials are project-agnostic),
        just swaps which project ID the provider's resource clients target.
        """
        self._project_id = project_id or ""

    async def list_accessible_projects(self) -> list[dict[str, str]]:
        """List every GCP project the current identity can see.

        Uses the Cloud Resource Manager v1 API via the generic
        google-api-python-client (already a dependency). Returns active
        projects only; empty list on any error.
        """
        if self._credentials is None and not await self.verify():
            return []

        return await asyncio.to_thread(self._sync_list_projects)

    def _sync_list_projects(self) -> list[dict[str, str]]:
        try:
            from googleapiclient import discovery
        except ImportError:
            logger.warning("google-api-python-client not available for project list")
            return []

        try:
            service = discovery.build(
                "cloudresourcemanager",
                "v1",
                credentials=self._credentials,
                cache_discovery=False,
            )
            projects: list[dict[str, str]] = []
            request = service.projects().list()
            while request is not None:
                response = request.execute()
                for p in response.get("projects", []):
                    if p.get("lifecycleState") != "ACTIVE":
                        continue
                    projects.append(
                        {
                            "project_id": p.get("projectId", ""),
                            "name": p.get("name", "") or p.get("projectId", ""),
                            "project_number": str(p.get("projectNumber", "")),
                        }
                    )
                request = service.projects().list_next(
                    previous_request=request, previous_response=response
                )
            projects.sort(key=lambda x: x["project_id"])
            return projects
        except Exception as exc:
            logger.warning("Could not list GCP projects: %s", exc)
            return []

    async def get_identity(self) -> dict[str, str]:
        """Return details about the authenticated GCP identity."""
        return {
            "project_id": self._project_id,
            "credential_type": type(self._credentials).__name__ if self._credentials else "none",
        }
