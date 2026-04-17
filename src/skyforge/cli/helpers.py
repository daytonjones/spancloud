"""Shared CLI helpers — profile switching, common options."""

from __future__ import annotations

import skyforge.providers  # noqa: F401
from skyforge.core.registry import registry


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
