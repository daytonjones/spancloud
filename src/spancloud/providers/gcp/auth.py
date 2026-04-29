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
            # Prefer explicit project from settings, then ADC project, then gcloud config.
            settings = get_settings().gcp
            self._project_id = settings.project_id or project or ""

            if not self._project_id:
                self._project_id = await asyncio.to_thread(self._detect_gcloud_project)

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

    @staticmethod
    def _detect_gcloud_project() -> str:
        """Read the active project from gcloud config file or CLI."""
        import configparser, os, subprocess
        # 1. Parse ~/.config/gcloud/configurations/config_<active>
        try:
            base = os.path.expanduser("~/.config/gcloud")
            active = "default"
            try:
                active = open(f"{base}/active_config").read().strip()
            except Exception:
                pass
            cp = configparser.ConfigParser()
            cp.read(f"{base}/configurations/config_{active}")
            project = cp.get("core", "project", fallback="")
            if project:
                return project
        except Exception:
            pass
        # 2. Ask the gcloud binary directly (works regardless of config path)
        try:
            result = subprocess.run(
                ["gcloud", "config", "get-value", "project"],
                capture_output=True, text=True, timeout=5,
            )
            project = result.stdout.strip()
            if project and project != "(unset)":
                return project
        except Exception:
            pass
        return ""

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
                    parent = p.get("parent", {})
                    org_id = parent.get("id", "") if parent.get("type") == "organization" else ""
                    projects.append(
                        {
                            "project_id": p.get("projectId", ""),
                            "name": p.get("name", "") or p.get("projectId", ""),
                            "project_number": str(p.get("projectNumber", "")),
                            "org_id": org_id,
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

    async def list_accessible_organizations(self) -> list[dict[str, str]]:
        """List GCP organizations the current identity can access.

        Only relevant for Google Workspace / Cloud Identity accounts.
        Personal Gmail accounts have no organizations. Returns empty list
        on any error or when no orgs are accessible.
        """
        if self._credentials is None and not await self.verify():
            return []
        return await asyncio.to_thread(self._sync_list_organizations)

    def _sync_list_organizations(self) -> list[dict[str, str]]:
        try:
            from googleapiclient import discovery
        except ImportError:
            return []

        try:
            service = discovery.build(
                "cloudresourcemanager",
                "v1",
                credentials=self._credentials,
                cache_discovery=False,
            )
            resp = service.organizations().search(body={"filter": ""}).execute()
            orgs = []
            for o in resp.get("organizations", []):
                if o.get("lifecycleState") != "ACTIVE":
                    continue
                # name field is "organizations/123456789"
                org_id = o.get("name", "").split("/")[-1]
                orgs.append({
                    "id": org_id,
                    "display_name": o.get("displayName", org_id),
                })
            return orgs
        except Exception as exc:
            logger.warning("Could not list GCP organizations: %s", exc)
            return []

    async def get_identity(self) -> dict[str, str]:
        """Return details about the authenticated GCP identity."""
        return {
            "project_id": self._project_id,
            "credential_type": type(self._credentials).__name__ if self._credentials else "none",
        }
