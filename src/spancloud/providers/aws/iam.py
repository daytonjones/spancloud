"""AWS IAM user, role, and policy resource discovery."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from skyforge.core.resource import Resource, ResourceState, ResourceType
from skyforge.utils.logging import get_logger
from skyforge.utils.retry import retry_with_backoff
from skyforge.utils.throttle import RateLimiter

if TYPE_CHECKING:
    from skyforge.providers.aws.auth import AWSAuth

logger = get_logger(__name__)

# IAM API is global, moderate rate limits
_IAM_LIMITER = RateLimiter(calls_per_second=8.0, max_concurrency=10)


class IAMUserResources:
    """Handles IAM user discovery."""

    def __init__(self, auth: AWSAuth) -> None:
        self._auth = auth

    @retry_with_backoff(max_retries=3, base_delay=1.0)
    async def list_users(self) -> list[Resource]:
        """List all IAM users.

        Returns:
            List of Resource objects representing IAM users.
        """
        client = self._auth.client("iam")

        def _fetch() -> list[dict[str, Any]]:
            users: list[dict[str, Any]] = []
            paginator = client.get_paginator("list_users")
            for page in paginator.paginate():
                users.extend(page.get("Users", []))
            return users

        async with _IAM_LIMITER:
            raw_users = await asyncio.to_thread(_fetch)

        resources: list[Resource] = []
        for user in raw_users:
            password_last_used = user.get("PasswordLastUsed")
            resources.append(Resource(
                id=user.get("UserId", ""),
                name=user.get("UserName", ""),
                resource_type=ResourceType.IAM,
                provider="aws",
                region="global",
                state=ResourceState.RUNNING,
                created_at=user.get("CreateDate"),
                tags={},
                metadata={
                    "arn": user.get("Arn", ""),
                    "path": user.get("Path", ""),
                    "password_last_used": (
                        str(password_last_used) if password_last_used else "never"
                    ),
                    "resource_subtype": "iam_user",
                },
            ))

        logger.debug("Found %d IAM users", len(resources))
        return resources


class IAMRoleResources:
    """Handles IAM role discovery."""

    def __init__(self, auth: AWSAuth) -> None:
        self._auth = auth

    @retry_with_backoff(max_retries=3, base_delay=1.0)
    async def list_roles(self) -> list[Resource]:
        """List all IAM roles.

        Returns:
            List of Resource objects representing IAM roles.
        """
        client = self._auth.client("iam")

        def _fetch() -> list[dict[str, Any]]:
            roles: list[dict[str, Any]] = []
            paginator = client.get_paginator("list_roles")
            for page in paginator.paginate():
                roles.extend(page.get("Roles", []))
            return roles

        async with _IAM_LIMITER:
            raw_roles = await asyncio.to_thread(_fetch)

        resources: list[Resource] = []
        for role in raw_roles:
            # Extract trusted entities from AssumeRolePolicyDocument
            trust_policy = role.get("AssumeRolePolicyDocument", {})
            trusted = self._extract_trusted_entities(trust_policy)

            resources.append(Resource(
                id=role.get("RoleId", ""),
                name=role.get("RoleName", ""),
                resource_type=ResourceType.IAM,
                provider="aws",
                region="global",
                state=ResourceState.RUNNING,
                created_at=role.get("CreateDate"),
                tags={},
                metadata={
                    "arn": role.get("Arn", ""),
                    "path": role.get("Path", ""),
                    "max_session_duration": str(
                        role.get("MaxSessionDuration", "")
                    ),
                    "trusted_entities": trusted,
                    "description": role.get("Description", ""),
                    "resource_subtype": "iam_role",
                },
            ))

        logger.debug("Found %d IAM roles", len(resources))
        return resources

    def _extract_trusted_entities(self, policy: dict[str, Any]) -> str:
        """Extract a summary of who can assume this role."""
        statements = policy.get("Statement", [])
        entities: list[str] = []
        for stmt in statements:
            principal = stmt.get("Principal", {})
            if isinstance(principal, str):
                entities.append(principal)
            elif isinstance(principal, dict):
                for key, val in principal.items():
                    if isinstance(val, list):
                        for v in val:
                            entities.append(f"{key}:{v.rsplit('/', 1)[-1]}")
                    else:
                        entities.append(f"{key}:{val.rsplit('/', 1)[-1]}")
        return ", ".join(entities[:5])


class IAMPolicyResources:
    """Handles IAM policy discovery (customer-managed only)."""

    def __init__(self, auth: AWSAuth) -> None:
        self._auth = auth

    @retry_with_backoff(max_retries=3, base_delay=1.0)
    async def list_policies(self) -> list[Resource]:
        """List customer-managed IAM policies.

        AWS-managed policies are excluded to reduce noise.

        Returns:
            List of Resource objects representing IAM policies.
        """
        client = self._auth.client("iam")

        def _fetch() -> list[dict[str, Any]]:
            policies: list[dict[str, Any]] = []
            paginator = client.get_paginator("list_policies")
            for page in paginator.paginate(Scope="Local"):
                policies.extend(page.get("Policies", []))
            return policies

        async with _IAM_LIMITER:
            raw_policies = await asyncio.to_thread(_fetch)

        resources: list[Resource] = []
        for pol in raw_policies:
            resources.append(Resource(
                id=pol.get("PolicyId", ""),
                name=pol.get("PolicyName", ""),
                resource_type=ResourceType.IAM,
                provider="aws",
                region="global",
                state=ResourceState.RUNNING,
                created_at=pol.get("CreateDate"),
                tags={},
                metadata={
                    "arn": pol.get("Arn", ""),
                    "path": pol.get("Path", ""),
                    "attachment_count": str(pol.get("AttachmentCount", 0)),
                    "is_attachable": str(pol.get("IsAttachable", True)),
                    "default_version": pol.get("DefaultVersionId", ""),
                    "description": pol.get("Description", ""),
                    "resource_subtype": "iam_policy",
                },
            ))

        logger.debug("Found %d customer-managed IAM policies", len(resources))
        return resources
