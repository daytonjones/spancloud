"""Check PyPI for a newer version of spancloud."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


async def get_latest_pypi_version(timeout: float = 5.0) -> str | None:
    """Fetch the latest spancloud version from PyPI. Returns None on any error."""
    import httpx
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get("https://pypi.org/pypi/spancloud/json")
            resp.raise_for_status()
            return resp.json()["info"]["version"]
    except Exception:
        return None


def is_newer(latest: str, current: str) -> bool:
    """Return True if latest is strictly newer than current (simple tuple comparison)."""
    try:
        def _parse(v: str) -> tuple[int, ...]:
            return tuple(int(x) for x in v.strip().split("."))
        return _parse(latest) > _parse(current)
    except Exception:
        return False


def upgrade_message(latest: str) -> str:
    return (
        f"A new version of Spancloud is available: v{latest}\n"
        f"Upgrade with:  pip install --upgrade spancloud"
    )
