"""AWS region discovery and multi-region parallel scanning."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from spancloud.utils.logging import get_logger
from spancloud.utils.retry import retry_with_backoff

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine

    from spancloud.core.resource import Resource
    from spancloud.providers.aws.auth import AWSAuth

logger = get_logger(__name__)

# Common regions to use as fallback if describe_regions fails.
DEFAULT_REGIONS = [
    "us-east-1",
    "us-east-2",
    "us-west-1",
    "us-west-2",
    "eu-west-1",
    "eu-west-2",
    "eu-central-1",
    "ap-southeast-1",
    "ap-southeast-2",
    "ap-northeast-1",
]


@retry_with_backoff(max_retries=2, base_delay=1.0)
async def get_enabled_regions(auth: AWSAuth) -> list[str]:
    """Discover all enabled AWS regions for the current account.

    Args:
        auth: Authenticated AWSAuth instance.

    Returns:
        Sorted list of enabled region names.
    """
    ec2 = auth.client("ec2")
    try:
        response = await asyncio.to_thread(
            ec2.describe_regions,
            Filters=[{"Name": "opt-in-status", "Values": ["opt-in-not-required", "opted-in"]}],
        )
        regions = sorted(r["RegionName"] for r in response.get("Regions", []))
        logger.debug("Discovered %d enabled AWS regions", len(regions))
        return regions
    except Exception as exc:
        logger.warning("Failed to discover regions, using defaults: %s", exc)
        return DEFAULT_REGIONS


async def scan_all_regions(
    auth: AWSAuth,
    fetch_fn: Callable[[str], Coroutine[None, None, list[Resource]]],
    regions: list[str] | None = None,
    max_concurrency: int = 10,
) -> list[Resource]:
    """Run a fetch function across all regions in parallel.

    Limits concurrency to avoid throttling. Failures in individual
    regions are logged and skipped rather than aborting the entire scan.

    Args:
        auth: Authenticated AWSAuth instance.
        fetch_fn: Async function taking a region name, returning resources.
        regions: Explicit region list. If None, discovers enabled regions.
        max_concurrency: Maximum number of concurrent region scans.

    Returns:
        Combined list of resources from all regions.
    """
    if regions is None:
        regions = await get_enabled_regions(auth)

    semaphore = asyncio.Semaphore(max_concurrency)
    all_resources: list[Resource] = []

    async def _scan_region(region: str) -> list[Resource]:
        async with semaphore:
            try:
                return await fetch_fn(region)
            except Exception as exc:
                logger.warning("Failed to scan region %s: %s", region, exc)
                return []

    tasks = [_scan_region(region) for region in regions]
    results = await asyncio.gather(*tasks)

    for region_resources in results:
        all_resources.extend(region_resources)

    logger.debug(
        "Multi-region scan complete: %d resources across %d regions",
        len(all_resources),
        len(regions),
    )
    return all_resources
