"""Interactive Alibaba Cloud login flow."""

from __future__ import annotations

import asyncio
import getpass

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt

console = Console()


async def alibaba_login() -> bool:
    """Prompt for Alibaba AccessKey ID + Secret, validate, persist."""
    console.print(
        Panel(
            "[bold cyan]Alibaba Cloud Authentication Setup[/bold cyan]\n\n"
            "Alibaba Cloud uses AccessKey ID + AccessKey Secret.\n"
            "Generate keys at: "
            "[link]https://ram.console.aliyun.com/manage/ak[/link]\n\n"
            "[dim]Use a RAM sub-user with least-privilege policies rather than "
            "your root account keys.[/dim]",
            title="Alibaba Login",
        )
    )

    from skyforge.config import get_settings
    from skyforge.utils import credentials

    settings = get_settings().alibaba

    # Check existing credentials
    existing_id = settings.access_key_id
    existing_secret = settings.access_key_secret
    source = "environment"
    if not (existing_id and existing_secret):
        stored_id = credentials.load("alibaba", "access_key_id")
        stored_secret = credentials.load("alibaba", "access_key_secret")
        if stored_id and stored_secret:
            existing_id = stored_id
            existing_secret = stored_secret
            source = f"credential store ({credentials.backend_name()})"

    if existing_id and existing_secret:
        id_tail = existing_id[-6:]
        console.print(
            f"\n[green]Existing AccessKey found[/green] "
            f"(id ending in ...{id_tail}, from {source})"
        )
        use_existing = input("Use existing key? [Y/n]: ").strip().lower()
        if use_existing in ("", "y", "yes"):
            region = Prompt.ask(
                "Region",
                default=settings.default_region,
                show_default=True,
            )
            ok = await _validate(existing_id, existing_secret, region)
            if ok:
                _persist(existing_id, existing_secret, region)
            return ok

    console.print()
    access_key_id = input("Enter your AccessKey ID: ").strip()
    if not access_key_id:
        console.print("[red]No AccessKey ID provided.[/red]")
        return False

    access_key_secret = getpass.getpass(
        "Enter your AccessKey Secret: "
    ).strip()
    if not access_key_secret:
        console.print("[red]No AccessKey Secret provided.[/red]")
        return False

    region = Prompt.ask(
        "Region",
        default=settings.default_region,
        show_default=True,
    )

    ok = await _validate(access_key_id, access_key_secret, region)
    if ok:
        _persist(access_key_id, access_key_secret, region)
    return ok


async def _validate(
    access_key_id: str, access_key_secret: str, region: str
) -> bool:
    """Validate credentials against ECS DescribeRegions."""
    console.print("[dim]Validating credentials...[/dim]")

    def _check() -> tuple[bool, str]:
        try:
            from alibabacloud_ecs20140526 import models as ecs_models
            from alibabacloud_ecs20140526.client import Client as EcsClient
            from alibabacloud_tea_openapi import models as open_api_models

            config = open_api_models.Config(
                access_key_id=access_key_id,
                access_key_secret=access_key_secret,
                endpoint=f"ecs.{region}.aliyuncs.com",
            )
            client = EcsClient(config)
            response = client.describe_regions(
                ecs_models.DescribeRegionsRequest()
            )
            regions_obj = getattr(response.body, "regions", None)
            count = len(getattr(regions_obj, "region", []) or []) if regions_obj else 0
            return True, f"Found {count} regions"
        except Exception as exc:
            return False, str(exc)

    ok, msg = await asyncio.to_thread(_check)
    if ok:
        console.print(f"\n[green]Authentication successful![/green] {msg}")
    else:
        console.print(f"[red]Authentication failed:[/red] {msg}")
    return ok


def _persist(access_key_id: str, access_key_secret: str, region: str) -> None:
    """Save verified credentials and region for future sessions."""
    from skyforge.utils import credentials

    ok_id = credentials.save("alibaba", "access_key_id", access_key_id)
    ok_sec = credentials.save("alibaba", "access_key_secret", access_key_secret)
    if ok_id and ok_sec:
        console.print(
            f"\n[dim]Credentials saved to {credentials.backend_name()}.[/dim]"
        )

    from skyforge.config import get_settings

    config_dir = get_settings().ensure_config_dir()
    env_path = config_dir / "alibaba.env"
    env_path.write_text(f"SKYFORGE_ALIBABA_DEFAULT_REGION={region}\n")

    import os

    os.environ["SKYFORGE_ALIBABA_DEFAULT_REGION"] = region
