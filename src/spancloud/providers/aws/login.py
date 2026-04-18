"""Interactive AWS login flows.

Supports SSO (with multi-account discovery), access keys, and profile switching.
"""

from __future__ import annotations

import configparser
import shutil
import subprocess
from enum import StrEnum
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table

from spancloud.utils.logging import get_logger

logger = get_logger(__name__)
console = Console()

AWS_CREDENTIALS_PATH = Path.home() / ".aws" / "credentials"
AWS_CONFIG_PATH = Path.home() / ".aws" / "config"


class AWSLoginMethod(StrEnum):
    """Available AWS authentication methods."""

    SSO = "sso"
    SSO_SETUP = "sso_setup"
    ACCESS_KEYS = "access_keys"
    PROFILE = "profile"


def _aws_cli_available() -> bool:
    """Check if the AWS CLI is installed."""
    return shutil.which("aws") is not None


def _get_existing_profiles() -> list[str]:
    """List AWS profiles from ~/.aws/credentials and ~/.aws/config."""
    profiles: set[str] = set()

    for path in (AWS_CREDENTIALS_PATH, AWS_CONFIG_PATH):
        if path.exists():
            config = configparser.ConfigParser()
            config.read(path)
            for section in config.sections():
                name = section.removeprefix("profile ").strip()
                if not name.startswith("sso-session"):
                    profiles.add(name)

    return sorted(profiles)


def _has_sso_profiles() -> bool:
    """Check if any SSO profiles are configured in ~/.aws/config."""
    if not AWS_CONFIG_PATH.exists():
        return False
    config = configparser.ConfigParser()
    config.read(AWS_CONFIG_PATH)
    return any(
        "sso_start_url" in config[s] or "sso_session" in config[s]
        for s in config.sections()
    )


def _get_sso_profiles() -> list[str]:
    """Return profile names that have SSO configuration."""
    if not AWS_CONFIG_PATH.exists():
        return []
    config = configparser.ConfigParser()
    config.read(AWS_CONFIG_PATH)
    profiles: list[str] = []
    for section in config.sections():
        if "sso_start_url" in config[section] or "sso_session" in config[section]:
            name = section.removeprefix("profile ").strip()
            if not name.startswith("sso-session"):
                profiles.append(name)
    return sorted(profiles)


def _get_sso_session_info() -> dict[str, str]:
    """Get the SSO session configuration (start URL, region)."""
    if not AWS_CONFIG_PATH.exists():
        return {}
    config = configparser.ConfigParser()
    config.read(AWS_CONFIG_PATH)
    for section in config.sections():
        if section.startswith("sso-session"):
            return {
                "session_name": section.removeprefix("sso-session ").strip(),
                "start_url": config[section].get("sso_start_url", ""),
                "region": config[section].get("sso_region", ""),
            }
        # Fallback: legacy format with sso_start_url directly in profile
        if "sso_start_url" in config[section]:
            return {
                "start_url": config[section].get("sso_start_url", ""),
                "region": config[section].get("sso_region", ""),
            }
    return {}


def choose_login_method() -> AWSLoginMethod:
    """Prompt the user to choose an AWS login method."""
    console.print()
    console.print(Panel("[bold cyan]AWS Authentication[/bold cyan]", expand=False))

    options: list[tuple[str, AWSLoginMethod, str]] = []

    if _has_sso_profiles():
        options.append(("SSO Login", AWSLoginMethod.SSO, "Log in with existing SSO profiles"))
        options.append((
            "SSO Setup All Accounts",
            AWSLoginMethod.SSO_SETUP,
            "Discover and configure all SSO accounts/roles",
        ))
    else:
        options.append((
            "SSO Setup",
            AWSLoginMethod.SSO_SETUP,
            "Configure AWS IAM Identity Center (SSO)",
        ))

    options.append(
        ("Access Keys", AWSLoginMethod.ACCESS_KEYS, "Enter AWS access key ID and secret key")
    )

    existing = _get_existing_profiles()
    if existing:
        options.append((
            "Switch Profile",
            AWSLoginMethod.PROFILE,
            f"Choose from {len(existing)} existing profiles",
        ))

    for i, (name, _, desc) in enumerate(options, 1):
        console.print(f"  [bold]{i}[/bold]) {name} — [dim]{desc}[/dim]")

    console.print()
    choice = Prompt.ask(
        "Select method",
        choices=[str(i) for i in range(1, len(options) + 1)],
        default="1",
    )

    return options[int(choice) - 1][1]


def login_sso() -> str | None:
    """Perform AWS SSO login using existing profiles.

    Returns:
        The profile name that was logged in, or None on failure.
    """
    if not _aws_cli_available():
        console.print("[red]AWS CLI is not installed.[/red] Install it from:")
        console.print(
            "  https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html"
        )
        return None

    sso_profiles = _get_sso_profiles()

    if not sso_profiles:
        console.print("[yellow]No SSO profiles found. Run SSO Setup first.[/yellow]")
        return None

    if len(sso_profiles) == 1:
        profile = sso_profiles[0]
        console.print(f"Using SSO profile: [bold]{profile}[/bold]")
    else:
        console.print("Available SSO profiles:")
        for i, p in enumerate(sso_profiles, 1):
            console.print(f"  [bold]{i}[/bold]) {p}")
        choice = Prompt.ask(
            "Select profile",
            choices=[str(i) for i in range(1, len(sso_profiles) + 1)],
        )
        profile = sso_profiles[int(choice) - 1]

    console.print(f"\n[cyan]Running:[/cyan] aws sso login --profile {profile}")
    console.print("[dim]This will open your browser for SSO authentication...[/dim]\n")

    result = subprocess.run(
        ["aws", "sso", "login", "--profile", profile],
        check=False,
    )

    if result.returncode == 0:
        console.print(f"\n[green]SSO login successful![/green] Profile: {profile}")
        console.print(
            f"[dim]Set SPANCLOUD_AWS_PROFILE={profile} to use this profile by default.[/dim]"
        )
        return profile

    console.print("\n[red]SSO login failed.[/red]")
    return None


def setup_sso_all_accounts() -> bool:
    """Discover all SSO accounts/roles and create profiles for each.

    Uses the SSO session to list all available accounts, then creates
    a named profile for each account+role combination.

    Returns:
        True if at least one profile was configured.
    """
    if not _aws_cli_available():
        console.print("[red]AWS CLI is not installed.[/red]")
        return False

    # Check for existing SSO session or set one up
    session_info = _get_sso_session_info()

    if not session_info.get("start_url"):
        console.print("[bold]First, let's configure your SSO connection.[/bold]\n")
        start_url = input("SSO start URL (e.g., https://your-org.awsapps.com/start): ").strip()
        if not start_url:
            console.print("[red]No URL provided.[/red]")
            return False
        sso_region = Prompt.ask("SSO region", default="us-east-1")
        session_name = Prompt.ask("SSO session name", default="spancloud")
    else:
        start_url = session_info["start_url"]
        sso_region = session_info.get("region", "us-east-1")
        session_name = session_info.get("session_name", "spancloud")
        console.print(f"Using existing SSO session: [bold]{session_name}[/bold]")
        console.print(f"  URL: {start_url}")
        console.print(f"  Region: {sso_region}\n")

    # Authenticate the SSO session first
    console.print("[cyan]Authenticating SSO session...[/cyan]")
    console.print("[dim]This will open your browser...[/dim]\n")

    # Make sure we have a session config
    _ensure_sso_session_config(session_name, start_url, sso_region)

    # Login using a profile that references this session (or the first SSO profile)
    sso_profiles = _get_sso_profiles()
    login_profile = sso_profiles[0] if sso_profiles else None

    if login_profile:
        result = subprocess.run(
            ["aws", "sso", "login", "--profile", login_profile],
            check=False,
        )
    else:
        # No profile yet — run aws configure sso for initial setup
        console.print("[yellow]No SSO profiles exist yet. Running initial setup...[/yellow]\n")
        result = subprocess.run(["aws", "configure", "sso"], check=False)
        if result.returncode == 0:
            console.print("\n[green]Initial SSO profile created.[/green]")
            return True
        console.print("\n[red]SSO setup failed.[/red]")
        return False

    if result.returncode != 0:
        console.print("[red]SSO authentication failed.[/red]")
        return False

    console.print("\n[green]SSO authenticated![/green] Discovering accounts...\n")

    # Use boto3 to list all SSO accounts
    try:
        import boto3

        sso_client = boto3.Session(region_name=sso_region).client("sso")

        # Get the SSO access token from the cached credentials
        token = _get_sso_access_token(start_url)
        if not token:
            console.print(
                "[yellow]Could not read SSO token. "
                "Profiles may need manual setup via 'aws configure sso'.[/yellow]"
            )
            return True  # SSO login itself succeeded

        # List all accounts
        accounts = []
        paginator_args = {"accessToken": token}
        while True:
            resp = sso_client.list_accounts(**paginator_args)
            accounts.extend(resp.get("accountList", []))
            next_token = resp.get("nextToken")
            if not next_token:
                break
            paginator_args["nextToken"] = next_token

        if not accounts:
            console.print("[yellow]No accounts found for this SSO session.[/yellow]")
            return True

        # Show accounts
        table = Table(
            title=f"Available SSO Accounts ({len(accounts)})",
            show_header=True,
            header_style="bold cyan",
        )
        table.add_column("#", width=3)
        table.add_column("Account ID")
        table.add_column("Account Name")
        table.add_column("Email")

        for i, acct in enumerate(accounts, 1):
            table.add_row(
                str(i),
                acct.get("accountId", ""),
                acct.get("accountName", ""),
                acct.get("emailAddress", ""),
            )

        console.print(table)

        # Ask which to configure
        if not Confirm.ask(
            f"\nCreate profiles for all {len(accounts)} accounts?", default=True
        ):
            console.print("[dim]You can run 'aws configure sso' for individual accounts.[/dim]")
            return True

        # Discover roles for each account and create profiles
        default_region = Prompt.ask("Default region for new profiles", default="us-east-1")
        created = 0

        for acct in accounts:
            acct_id = acct.get("accountId", "")
            acct_name = acct.get("accountName", "")

            try:
                roles_resp = sso_client.list_account_roles(
                    accessToken=token,
                    accountId=acct_id,
                )
                roles = roles_resp.get("roleList", [])
            except Exception as exc:
                console.print(f"  [yellow]Could not list roles for {acct_name}: {exc}[/yellow]")
                continue

            for role in roles:
                role_name = role.get("roleName", "")
                # Create a readable profile name
                safe_name = acct_name.replace(" ", "-").lower()
                profile_name = f"{safe_name}-{role_name}" if len(roles) > 1 else safe_name

                _write_sso_profile(
                    profile_name=profile_name,
                    session_name=session_name,
                    account_id=acct_id,
                    role_name=role_name,
                    region=default_region,
                )
                console.print(
                    f"  [green]+[/green] {profile_name} "
                    f"[dim]({acct_id} / {role_name})[/dim]"
                )
                created += 1

        console.print(f"\n[bold green]{created} profile(s) created![/bold green]")
        console.print(
            "[dim]Use 'spancloud profile list' to see all profiles, "
            "or --profile <name> on any command.[/dim]"
        )
        return True

    except Exception as exc:
        console.print(f"[yellow]Account discovery failed: {exc}[/yellow]")
        console.print("[dim]SSO login succeeded — you can still use existing profiles.[/dim]")
        return True


def _ensure_sso_session_config(
    session_name: str, start_url: str, sso_region: str
) -> None:
    """Ensure the sso-session block exists in ~/.aws/config."""
    AWS_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    config = configparser.ConfigParser()
    if AWS_CONFIG_PATH.exists():
        config.read(AWS_CONFIG_PATH)

    section = f"sso-session {session_name}"
    if section not in config:
        config[section] = {}

    config[section]["sso_start_url"] = start_url
    config[section]["sso_region"] = sso_region
    config[section]["sso_registration_scopes"] = "sso:account:access"

    with AWS_CONFIG_PATH.open("w") as f:
        config.write(f)


def _write_sso_profile(
    profile_name: str,
    session_name: str,
    account_id: str,
    role_name: str,
    region: str,
) -> None:
    """Write a single SSO profile to ~/.aws/config."""
    config = configparser.ConfigParser()
    if AWS_CONFIG_PATH.exists():
        config.read(AWS_CONFIG_PATH)

    section = f"profile {profile_name}"
    if section not in config:
        config[section] = {}

    config[section]["sso_session"] = session_name
    config[section]["sso_account_id"] = account_id
    config[section]["sso_role_name"] = role_name
    config[section]["region"] = region

    with AWS_CONFIG_PATH.open("w") as f:
        config.write(f)


def _get_sso_access_token(start_url: str) -> str | None:
    """Read the cached SSO access token from ~/.aws/sso/cache/.

    The AWS CLI caches SSO tokens as JSON files in this directory.
    """
    import json

    cache_dir = Path.home() / ".aws" / "sso" / "cache"
    if not cache_dir.exists():
        return None

    # Try all cached tokens — find one matching our start URL
    for cache_file in cache_dir.glob("*.json"):
        try:
            data = json.loads(cache_file.read_text())
            if data.get("startUrl", "") == start_url or data.get("accessToken"):
                token = data.get("accessToken")
                if token:
                    return token
        except (json.JSONDecodeError, KeyError):
            continue

    return None


def login_access_keys() -> str | None:
    """Prompt for AWS access keys and write them to ~/.aws/credentials.

    Returns:
        The profile name, or None on failure.
    """
    console.print()
    console.print("[bold]Enter your AWS credentials:[/bold]")
    console.print("[dim]These will be saved to ~/.aws/credentials[/dim]\n")

    access_key = Prompt.ask("AWS Access Key ID")
    secret_key = Prompt.ask("AWS Secret Access Key", password=True)
    region = Prompt.ask("Default region", default="us-east-1")

    profile = Prompt.ask("Profile name", default="default")

    # Write credentials
    AWS_CREDENTIALS_PATH.parent.mkdir(parents=True, exist_ok=True)

    cred_config = configparser.ConfigParser()
    if AWS_CREDENTIALS_PATH.exists():
        cred_config.read(AWS_CREDENTIALS_PATH)

    if profile not in cred_config:
        cred_config[profile] = {}

    cred_config[profile]["aws_access_key_id"] = access_key
    cred_config[profile]["aws_secret_access_key"] = secret_key

    with AWS_CREDENTIALS_PATH.open("w") as f:
        cred_config.write(f)

    # Also set the region in config
    aws_config = configparser.ConfigParser()
    if AWS_CONFIG_PATH.exists():
        aws_config.read(AWS_CONFIG_PATH)

    config_section = profile if profile == "default" else f"profile {profile}"
    if config_section not in aws_config:
        aws_config[config_section] = {}

    aws_config[config_section]["region"] = region

    with AWS_CONFIG_PATH.open("w") as f:
        aws_config.write(f)

    console.print(f"\n[green]Credentials saved![/green] Profile: [bold]{profile}[/bold]")

    if profile != "default":
        console.print(
            f"[dim]Set SPANCLOUD_AWS_PROFILE={profile} to use this profile by default.[/dim]"
        )

    return profile


def login_profile() -> str | None:
    """Switch to an existing AWS profile.

    Returns:
        The selected profile name, or None on failure.
    """
    profiles = _get_existing_profiles()
    if not profiles:
        console.print("[yellow]No existing AWS profiles found.[/yellow]")
        return None

    console.print("\n[bold]Available profiles:[/bold]")
    for i, p in enumerate(profiles, 1):
        console.print(f"  [bold]{i}[/bold]) {p}")

    choice = Prompt.ask(
        "\nSelect profile",
        choices=[str(i) for i in range(1, len(profiles) + 1)],
    )
    profile = profiles[int(choice) - 1]

    console.print(f"\n[green]Selected profile:[/green] [bold]{profile}[/bold]")
    console.print(f"Set SPANCLOUD_AWS_PROFILE={profile} to use this profile.")
    console.print(f"Or run: [cyan]export AWS_PROFILE={profile}[/cyan]")

    if Confirm.ask("Set AWS_PROFILE for this session via env export hint?", default=True):
        console.print(f"\n[bold]Run this in your shell:[/bold]\n  export AWS_PROFILE={profile}")

    return profile


def _check_existing_credentials() -> dict[str, str] | None:
    """Check if existing AWS credentials are valid."""
    try:
        import boto3

        session = boto3.Session()
        sts = session.client("sts")
        identity = sts.get_caller_identity()
        return {
            "account": identity.get("Account", "unknown"),
            "arn": identity.get("Arn", "unknown"),
        }
    except Exception:
        return None


def aws_login() -> str | None:
    """Run the interactive AWS login flow.

    Detects existing valid credentials and offers to skip re-authentication.
    For SSO users with multiple accounts, discovers all accounts/roles and
    creates profiles for each.

    Returns:
        The profile name that was authenticated, or None on failure.
        Returns "default" for pre-existing credentials.
    """
    console.print()
    console.print(Panel("[bold cyan]AWS Authentication[/bold cyan]", expand=False))

    # Check for existing valid credentials
    console.print("[dim]Checking existing credentials...[/dim]")
    existing = _check_existing_credentials()

    if existing:
        console.print(
            f"\n[green]Already authenticated![/green]\n"
            f"  Account: [bold]{existing['account']}[/bold]\n"
            f"  ARN:     [bold]{existing['arn']}[/bold]"
        )
        if not Confirm.ask("\nRe-authenticate or switch credentials?", default=False):
            return "default"

    method = choose_login_method()

    match method:
        case AWSLoginMethod.SSO:
            return login_sso()
        case AWSLoginMethod.SSO_SETUP:
            # setup_sso_all_accounts creates many profiles, return first SSO profile
            if setup_sso_all_accounts():
                sso_profiles = _get_sso_profiles()
                return sso_profiles[0] if sso_profiles else "default"
            return None
        case AWSLoginMethod.ACCESS_KEYS:
            return login_access_keys()
        case AWSLoginMethod.PROFILE:
            return login_profile()
    return None
