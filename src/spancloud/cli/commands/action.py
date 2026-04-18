"""CLI commands for resource actions (start, stop, reboot, terminate)."""

from __future__ import annotations

import asyncio

import typer
from rich.console import Console

import spancloud.providers  # noqa: F401
from spancloud.core.registry import registry

console = Console()
action_app = typer.Typer(
    help="Perform actions on cloud resources (start, stop, reboot, terminate).",
    no_args_is_help=True,
)


def _run_action(
    verb: str,
    provider_name: str,
    instance_id: str,
    region: str | None,
    force: bool,
) -> None:
    """Common logic for all resource actions."""
    provider = registry.get(provider_name)
    if not provider or provider_name not in (
        "aws", "gcp", "vultr", "digitalocean", "azure", "oci", "alibaba"
    ):
        console.print(
            f"[yellow]Resource actions not available for '{provider_name}'.[/yellow]"
        )
        raise typer.Exit(code=1)

    # Terminate support varies
    if provider_name == "gcp" and verb == "terminate":
        console.print(
            "[yellow]GCP does not support 'terminate'. "
            "Use 'stop' or delete via the console.[/yellow]"
        )
        raise typer.Exit(code=1)

    if provider_name == "vultr" and verb == "terminate":
        console.print(
            "[yellow]Vultr does not support 'terminate' via API. "
            "Use the Vultr console to destroy instances.[/yellow]"
        )
        raise typer.Exit(code=1)

    if provider_name == "digitalocean" and verb == "terminate":
        console.print(
            "[yellow]DigitalOcean does not support 'terminate' via this CLI. "
            "Use the DO console to destroy droplets.[/yellow]"
        )
        raise typer.Exit(code=1)

    if provider_name == "azure" and verb == "terminate":
        console.print(
            "[yellow]Azure VM 'terminate' (delete) is not exposed here. "
            "Use 'az vm delete' or the Azure portal.[/yellow]"
        )
        raise typer.Exit(code=1)

    if provider_name == "oci" and verb == "terminate":
        console.print(
            "[yellow]OCI 'terminate' (delete) is not exposed here. "
            "Use the OCI console or `oci compute instance terminate`.[/yellow]"
        )
        raise typer.Exit(code=1)

    if provider_name == "alibaba" and verb == "terminate":
        console.print(
            "[yellow]Alibaba 'terminate' (DeleteInstance) is not exposed here. "
            "Use the Alibaba console.[/yellow]"
        )
        raise typer.Exit(code=1)

    gcp_verb = "reset" if provider_name == "gcp" and verb == "reboot" else verb

    async def _preflight():
        await provider.authenticate()

        if provider_name == "aws":
            from spancloud.providers.aws.actions import EC2Actions

            handler = EC2Actions(provider._auth)
            info = await handler.get_instance_state(instance_id, region)
            return handler, info, "aws"
        elif provider_name == "gcp":
            from spancloud.providers.gcp.actions import GCEActions

            if not region:
                console.print(
                    "[red]Zone is required for GCP actions "
                    "(--region us-central1-a)[/red]"
                )
                raise typer.Exit(code=1)
            handler = GCEActions(provider._auth)
            info = await handler.get_instance_state(instance_id, region)
            return handler, info, "gcp"
        elif provider_name == "vultr":
            from spancloud.providers.vultr.actions import VultrActions

            handler = VultrActions(provider._auth)
            info = await handler.get_instance_state(instance_id)
            return handler, info, "vultr"
        elif provider_name == "digitalocean":
            from spancloud.providers.digitalocean.actions import DropletActions

            handler = DropletActions(provider._auth)
            info = await handler.get_droplet_state(instance_id)
            return handler, info, "digitalocean"
        elif provider_name == "azure":
            from spancloud.providers.azure.actions import VMActions

            handler = VMActions(provider._auth)
            info = await handler.get_instance_state(instance_id, region)
            return handler, info, "azure"
        elif provider_name == "oci":
            from spancloud.providers.oci.actions import InstanceActions

            handler = InstanceActions(provider._auth)
            info = await handler.get_instance_state(instance_id, region)
            return handler, info, "oci"
        else:  # alibaba
            from spancloud.providers.alibaba.actions import ECSActions

            handler = ECSActions(provider._auth)
            info = await handler.get_instance_state(instance_id, region)
            return handler, info, "alibaba"

    # Get current state first
    with console.status(f"[bold cyan]Checking instance {instance_id}..."):
        try:
            actions_handler, info, prov = asyncio.run(_preflight())
        except Exception as exc:
            console.print(f"[red]Error:[/red] {exc}")
            raise typer.Exit(code=1) from exc

    name = info["name"]
    state = info["state"]
    inst_type = info.get("instance_type", info.get("machine_type", ""))

    # Confirmation prompt (terminate always requires confirmation)
    if verb == "terminate":
        console.print("[bold red]WARNING: TERMINATE[/bold red] is irreversible!")
        console.print(f"  Instance: [bold]{name}[/bold] ({instance_id})")
        console.print(f"  Type: {inst_type}  |  Region: {region or 'default'}")
        if not force:
            confirm = typer.confirm(
                f"Are you sure you want to terminate '{name}'?"
            )
            if not confirm:
                console.print("[yellow]Aborted.[/yellow]")
                raise typer.Exit(code=0)
    elif not force:
        console.print(
            f"  Action: [bold]{verb}[/bold] → {name} ({instance_id}, {state})"
        )
        confirm = typer.confirm(f"Proceed with {verb}?")
        if not confirm:
            console.print("[yellow]Aborted.[/yellow]")
            raise typer.Exit(code=0)

    # Execute
    async def _execute():
        if prov == "aws":
            from spancloud.providers.aws.actions import ActionVerb as AWSVerb

            return await actions_handler.execute(
                AWSVerb(verb), instance_id, region
            )
        elif prov == "gcp":
            from spancloud.providers.gcp.actions import ActionVerb as GCPVerb

            return await actions_handler.execute(
                GCPVerb(gcp_verb), instance_id, region
            )
        elif prov == "vultr":
            from spancloud.providers.vultr.actions import ActionVerb as VultrVerb

            # Map 'stop' to 'halt', 'reboot' stays 'reboot'
            vultr_verb = "halt" if verb == "stop" else verb
            return await actions_handler.execute(
                VultrVerb(vultr_verb), instance_id
            )
        elif prov == "digitalocean":
            from spancloud.providers.digitalocean.actions import (
                ActionVerb as DOVerb,
            )

            # Map 'start' → 'power_on', 'stop' → 'power_off'
            do_verb_map = {
                "start": "power_on",
                "stop": "power_off",
                "reboot": "reboot",
            }
            do_verb = do_verb_map.get(verb, verb)
            return await actions_handler.execute(
                DOVerb(do_verb), instance_id
            )
        elif prov == "azure":
            from spancloud.providers.azure.actions import (
                ActionVerb as AzVerb,
            )

            # Azure 'stop' maps to 'deallocate' (cost-saving stop);
            # 'reboot' → 'restart'.
            az_verb_map = {
                "start": "start",
                "stop": "deallocate",
                "reboot": "restart",
            }
            az_verb = az_verb_map.get(verb, verb)
            return await actions_handler.execute(
                AzVerb(az_verb), instance_id, region
            )
        elif prov == "oci":
            from spancloud.providers.oci.actions import (
                ActionVerb as OCIVerb,
            )

            # OCI 'reboot' maps to SOFTRESET; 'start' → START; 'stop' → SOFTSTOP
            oci_verb_map = {
                "start": "START",
                "stop": "SOFTSTOP",
                "reboot": "SOFTRESET",
            }
            oci_verb = oci_verb_map.get(verb, verb.upper())
            return await actions_handler.execute(
                OCIVerb(oci_verb), instance_id, region
            )
        else:  # alibaba
            from spancloud.providers.alibaba.actions import (
                ActionVerb as AliVerb,
            )

            return await actions_handler.execute(
                AliVerb(verb), instance_id, region
            )

    with console.status(f"[bold cyan]Sending {verb} to {name}..."):
        try:
            result = asyncio.run(_execute())
        except Exception as exc:
            console.print(f"[red]Error:[/red] {exc}")
            raise typer.Exit(code=1) from exc

    if result.success:
        console.print(f"[green]{result.message}[/green]")
    else:
        console.print(f"[red]{result.message}[/red]")
        raise typer.Exit(code=1)


@action_app.command("start")
def start_instance(
    instance_id: str = typer.Argument(
        help="Instance ID (EC2 / GCE / Droplet / VM / ECS / Vultr / OCI OCID)."
    ),
    provider_name: str = typer.Option(
        "aws", "--provider", "-p",
        help="Provider: aws, gcp, vultr, digitalocean, azure, oci, alibaba.",
    ),
    region: str | None = typer.Option(
        None, "--region", "-r",
        help="Region (or zone for GCP/OCI). Required for GCP and Azure.",
    ),
    force: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation."),
) -> None:
    """Start a stopped compute instance."""
    _run_action("start", provider_name, instance_id, region, force)


@action_app.command("stop")
def stop_instance(
    instance_id: str = typer.Argument(
        help="Instance ID (EC2 / GCE / Droplet / VM / ECS / Vultr / OCI OCID)."
    ),
    provider_name: str = typer.Option(
        "aws", "--provider", "-p",
        help="Provider: aws, gcp, vultr, digitalocean, azure, oci, alibaba.",
    ),
    region: str | None = typer.Option(
        None, "--region", "-r",
        help="Region (or zone for GCP/OCI). Required for GCP and Azure.",
    ),
    force: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation."),
) -> None:
    """Stop a running compute instance."""
    _run_action("stop", provider_name, instance_id, region, force)


@action_app.command("reboot")
def reboot_instance(
    instance_id: str = typer.Argument(
        help="Instance ID (EC2 / GCE / Droplet / VM / ECS / Vultr / OCI OCID)."
    ),
    provider_name: str = typer.Option(
        "aws", "--provider", "-p",
        help="Provider: aws, gcp, vultr, digitalocean, azure, oci, alibaba.",
    ),
    region: str | None = typer.Option(
        None, "--region", "-r",
        help="Region (or zone for GCP/OCI). Required for GCP and Azure.",
    ),
    force: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation."),
) -> None:
    """Reboot a running compute instance."""
    _run_action("reboot", provider_name, instance_id, region, force)


@action_app.command("terminate")
def terminate_instance(
    instance_id: str = typer.Argument(
        help="Instance ID (EC2 / GCE / Droplet / VM / ECS / Vultr / OCI OCID)."
    ),
    provider_name: str = typer.Option(
        "aws", "--provider", "-p",
        help="Provider: aws, gcp, vultr, digitalocean, azure, oci, alibaba.",
    ),
    region: str | None = typer.Option(
        None, "--region", "-r",
        help="Region (or zone for GCP/OCI). Required for GCP and Azure.",
    ),
    force: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation."),
) -> None:
    """Terminate an instance (AWS only — all other providers reject this)."""
    _run_action("terminate", provider_name, instance_id, region, force)
