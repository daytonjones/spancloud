"""Shared CLI helpers — profile switching, common options."""

from __future__ import annotations

import spancloud.providers  # noqa: F401
from spancloud.core.registry import registry


def apply_aws_profile(profile: str | None) -> None:
    """Set the active AWS profile if specified.

    Call this at the start of any command that accepts --profile.

    Args:
        profile: AWS profile name, or None to use default/env.
    """
    if profile:
        aws = registry.get("aws")
        if aws:
            aws._auth.set_profile(profile)


def apply_gcp_project(project: str | None) -> None:
    """Set the active GCP project if specified.

    Call this at the start of any command that accepts --gcp-project.
    ADC credentials are project-agnostic, so this just swaps which
    project the provider's clients target.

    Args:
        project: GCP project ID, or None to use ADC/env default.
    """
    if project:
        gcp = registry.get("gcp")
        if gcp:
            gcp._auth.set_project(project)
