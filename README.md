# Spancloud

[![GitHub stars](https://img.shields.io/github/stars/daytonjones/spancloud?style=flat-square)](https://github.com/daytonjones/spancloud/stargazers)
[![GitHub forks](https://img.shields.io/github/forks/daytonjones/spancloud?style=flat-square)](https://github.com/daytonjones/spancloud/network/members)
[![GitHub watchers](https://img.shields.io/github/watchers/daytonjones/spancloud?style=flat-square)](https://github.com/daytonjones/spancloud/watchers)
[![GitHub issues](https://img.shields.io/github/issues/daytonjones/spancloud?style=flat-square)](https://github.com/daytonjones/spancloud/issues)
[![GitHub license](https://img.shields.io/github/license/daytonjones/spancloud?style=flat-square)](https://github.com/daytonjones/spancloud/blob/main/LICENSE)
[![Python](https://img.shields.io/badge/python-3.12+-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-D7FF64?style=flat-square&logo=ruff&logoColor=D7FF64)](https://docs.astral.sh/ruff/)
[![Type checked: mypy](https://img.shields.io/badge/type%20checked-mypy-blue?style=flat-square)](https://mypy-lang.org/)
[![Platform](https://img.shields.io/badge/platform-linux%20%7C%20macOS%20%7C%20windows-lightgrey?style=flat-square)]()
[![Architecture](https://img.shields.io/badge/architecture-multi--cloud-blueviolet?style=flat-square)]()
[![Providers](https://img.shields.io/badge/providers-AWS%20%7C%20GCP%20%7C%20Azure%20%7C%20OCI%20%7C%20DO%20%7C%20Vultr-orange?style=flat-square)]()
[![TUI](https://img.shields.io/badge/TUI-Textual-1F6FEB?style=flat-square)](https://textual.textualize.io/)
[![GUI](https://img.shields.io/badge/GUI-PySide6%20%28Qt6%29-41CD52?style=flat-square&logo=qt&logoColor=white)](https://doc.qt.io/qtforpython/)
[![Works on my machine](https://img.shields.io/badge/works-on%20my%20machine-brightgreen?style=flat-square)]()

Multi-cloud infrastructure orchestrator — an all-seeing eye into your cloud resources.

Spancloud provides a unified interface to discover, inspect, and manage infrastructure across multiple cloud providers from a single CLI, TUI, or desktop GUI.

## Supported Providers

| Provider | Status | Resource Types |
|----------|--------|---------------|
| **AWS** (Amazon Web Services) | Implemented | Compute (EC2), Storage (S3), Network (VPC/Subnet/SG), Database (RDS/Aurora), Serverless (Lambda), Load Balancers (ALB/NLB/CLB), Containers (EKS), DNS (Route53), IAM (Users/Roles/Policies) |
| **GCP** (Google Cloud Platform) | Implemented | Compute (GCE), Storage (GCS), Network (VPC/Subnet/Firewall), Database (Cloud SQL), Serverless (Cloud Functions/Cloud Run), Load Balancers, Containers (GKE), DNS (Cloud DNS) |
| **Vultr** | Implemented | Compute (Instances/Bare Metal), Storage (Block/Object), Network (VPC/Firewall), Database (Managed), Containers (VKE), Load Balancers, DNS |
| **Digital Ocean** | Implemented | Compute (Droplets), Storage (Volumes/Spaces), Network (VPC/Firewall), Database (Managed), Containers (DOKS), Load Balancers, DNS |
| **Azure** (Microsoft Azure) | Implemented | Compute (VMs), Storage (Blob), Network (VNet/NSG/Public IP), Database (Azure SQL/Cosmos DB), Serverless (App Service/Functions), Containers (AKS), Load Balancers, DNS |
| **Oracle Cloud** (OCI) | Implemented | Compute (Instances), Storage (Object Storage + Block Volumes), Network (VCN/Subnet/Security List/NSG), Database (Autonomous DB + DB Systems), Containers (OKE), Load Balancers (LB + NLB), DNS Zones |
| **Alibaba Cloud** | Coming Soon | — |

## Installation

Requires Python 3.12+.

```bash
pip install spancloud
```

After install, two entry points are available:

```bash
spancloud          # Launch desktop GUI (default; requires PySide6)
sc                 # Short alias — identical to spancloud
spancloud --tui    # Launch TUI instead
spancloud --help   # Show all CLI commands
```

## Quick Start

### Desktop GUI

```bash
pip install spancloud
spancloud               # Default — launches GUI
sc                      # Short alias, also launches GUI
spancloud gui           # Explicit GUI launch
spancloud --tui         # Launch TUI instead
```

The desktop GUI provides a native Qt6 window with:

- **Full-width toolbar** — icon, app name, current context breadcrumb, refresh and settings buttons
- **Resizable sidebar** — provider list with colour-coded connection status dots; drag the splitter handle to adjust width
- **Overview dashboard** — provider cards in a 3-column grid showing live resource count, connection state, and a colour-coded breakdown bar by resource type
- **Per-provider view** — inner nav sidebar with RESOURCES (Compute, Storage, …) and ANALYSIS (Cost Summary, Security Audit, Unused Resources, Relationships, Monitoring Alerts) sections, each with resource count badges
- **Resource table** — Name / ID / State / Region / Type columns; State column colour-coded (green=running, red=stopped, yellow=pending); click any column header to sort
- **Right-side detail drawer** — click any table row to open a scrollable key-value panel; close with ✕ or by clicking another resource type
- **Metrics panel** — select a resource row then open the Metrics analysis to see live CloudWatch / provider time-series charts with sparklines
- **Relationships panel** — visualises resource dependency graphs (e.g. EC2 → VPC → Subnet → Security Group) as an inline tree
- **Analysis panels** — cost breakdown, security findings, unused resources, monitoring alerts, all fetched live from the provider API
- **Settings dialog** — toggle providers on/off; choose from 5 built-in themes (Tokyo Night, Dark, Dracula, Solarized Dark, Light)
- **Status bar** — active context on the left, total provider/resource count on the right
- **Region / profile / project selectors** — switch AWS region or profile, GCP project inline without relaunching
- **Demo mode** — run `spancloud --mock` to explore with realistic sample data, no credentials needed; works in both GUI (`spancloud gui --mock`) and TUI (`spancloud --tui --mock`)

#### Screenshots

| Overview | Provider View |
|---|---|
| ![Overview](https://raw.githubusercontent.com/daytonjones/spancloud/main/docs/screenshots/gui-overview.png) | ![Provider View](https://raw.githubusercontent.com/daytonjones/spancloud/main/docs/screenshots/gui-provider.png) |

| Resource Table + Detail Drawer | Metrics Panel |
|---|---|
| ![Resource Table](https://raw.githubusercontent.com/daytonjones/spancloud/main/docs/screenshots/gui-resources.png) | ![Metrics](https://raw.githubusercontent.com/daytonjones/spancloud/main/docs/screenshots/gui-metrics.png) |

### TUI Dashboard

```bash
spancloud --tui         # Launch TUI (GUI is the default)
spancloud tui           # Also launches TUI explicitly
```

The TUI provides:
- **Tabbed layout** — Overview tab + one tab per enabled provider (AWS, GCP, Vultr, DigitalOcean, Azure, OCI)
- **Region selector** — every provider tab has a region dropdown in the sidebar
- **AWS profile switcher** — extra dropdown on the AWS tab for multi-account users
- **GCP project switcher** — extra dropdown on the GCP tab populated from Cloud Resource Manager; swap between every project the signed-in identity can see
- **Resource type sidebar** — emoji-labeled resource types + analysis tools, click or Enter to load
- **Resource detail panel** — click any row to see full metadata, tags, and state in a bottom panel
- **State-colored rows** — green=running, red=stopped, yellow=pending, dim=terminated
- **Search/filter** — press `/` to search across name, type, region, metadata; filters live as you type
- **Export** — `e` on any loaded table writes JSON / CSV / YAML to disk
- **Analysis views** — cost summary, security audit, unused resources, relationships, and monitoring alerts inline per provider
- **Settings screen** — click the Settings sidebar item to pick which resource types appear; matches `spancloud config sidebar`
- **Provider enable/disable** — `spancloud config providers` (or the settings screen) hides tabs you don't use
- **Animated progress** — slow analysis runs show a spinner + elapsed timer so you know Vultr / large Azure subs are still working
- **Auth modals** — click any unauthenticated provider tile on the Overview tab to log in; Vultr / DO save tokens to the OS keychain for the next session
- **Keyboard navigation** — Tab/Shift+Tab providers, Up/Down sidebar, Enter to load, `/` search, `e` export, Escape close, `?` help, `q` quit
- **Mouse support** — click sidebar items, table rows, dropdowns, search input

#### Terminal Setup

For the best TUI experience, configure your terminal:

**iTerm2 (macOS):**
- **Profiles > Terminal > Enable mouse reporting** — must be checked for mouse/click support
- **Profiles > General > Title** — set to "Session Name" or include "Terminal Title" to see `Spancloud :: <provider>` in the tab

**Terminal.app (macOS):**
- **Profiles > Window > Title** — check "Active process name"

### CLI Usage

```bash
# Authenticate with a cloud provider (interactive)
spancloud auth login aws                         # SSO, access keys, or profile selection
spancloud auth login gcp                         # Application Default Credentials + project setup
spancloud auth login vultr                       # API key
spancloud auth login digitalocean                # Personal Access Token
spancloud auth login azure                       # Wraps 'az login' + subscription selection
spancloud auth login oci                         # Reads ~/.oci/config or shells to 'oci setup config'

# Check auth status for all providers at once
spancloud auth status

# List all registered providers
spancloud provider list

# Check detailed status for a single provider
spancloud provider status aws
spancloud provider status gcp

# List resources by type
spancloud resource list aws compute
spancloud resource list aws storage
spancloud resource list aws network              # VPCs, subnets, security groups
spancloud resource list aws database             # RDS instances + Aurora clusters
spancloud resource list aws serverless           # Lambda functions
spancloud resource list aws load_balancer        # ALB, NLB, Classic ELBs
spancloud resource list aws container            # EKS clusters, node groups, Fargate profiles

# Filter by region
spancloud resource list aws compute --region us-west-2
spancloud resource list gcp compute --region us-central1
spancloud resource list gcp network              # VPC networks, subnets, firewall rules
spancloud resource list gcp database             # Cloud SQL instances
spancloud resource list gcp serverless           # Cloud Functions + Cloud Run services
spancloud resource list gcp container            # GKE clusters + node pools
spancloud resource list gcp load_balancer        # Forwarding rules + backend services

# Scan ALL regions at once
spancloud resource list aws compute --all-regions

# Filter by tags
spancloud resource list aws compute --tag env=prod
spancloud resource list aws compute --tag env=prod --tag team=platform

# Combine filters
spancloud resource list aws compute --all-regions --tag env=prod

# Show details for a specific resource
spancloud resource show aws compute i-0abc123def --region us-east-1

# Export to JSON / CSV / YAML (to stdout or a file)
spancloud resource list aws compute --export json
spancloud resource list aws compute --export csv -o ec2.csv
spancloud resource list gcp compute --export yaml

# Show version
spancloud version

# Cost analysis (--profile for multi-account)
spancloud cost show aws                         # 30-day cost summary with daily trend
spancloud cost show aws --days 7                # Last 7 days
spancloud cost show aws --profile production    # Costs for a specific account
spancloud cost show gcp                         # GCP billing info + BigQuery export

# Security audit
spancloud audit run aws                         # Scan for misconfigurations
spancloud audit run aws --region us-west-2      # Region-specific scan
spancloud audit run gcp                         # GCP firewall, GCS, Cloud SQL checks

# Unused resource detection
spancloud unused scan aws                       # Find idle/orphaned resources
spancloud unused scan gcp --stopped-days 14     # Custom threshold for stopped VMs
spancloud unused scan aws --snapshot-days 60    # Snapshots older than 60 days

# Resource relationship mapping
spancloud map show aws                          # Table of all relationships
spancloud map show aws --tree                   # Tree view
spancloud map show aws --resource i-0abc123def  # Relationships for one resource
spancloud map show gcp --region us-central1     # GCP relationships

# --- Resource actions (start / stop / reboot / terminate) ---
# All seven providers support start/stop/reboot. Only AWS supports terminate.
spancloud action start i-0abc123 --region us-east-1
spancloud action start my-vm -p gcp --region us-central1-a
spancloud action stop <droplet-id> -p digitalocean
spancloud action reboot web-1 -p azure --region eastus
spancloud action start <ocid> -p oci --region us-ashburn-1
spancloud action stop <id> -p vultr
spancloud action terminate i-0abc123            # AWS only — requires confirmation
spancloud action start i-0abc123 --yes          # -y skips the confirmation prompt

# --- Provider-specific detail viewers ---

# S3 / GCS / Vultr Block + Object Storage detail pages
spancloud s3 info my-bucket                     # Policy, lifecycle, size, encryption
spancloud gcs info my-bucket                    # IAM, lifecycle, size, encryption
spancloud vultr block-info <block-id>           # Vultr block storage detail
spancloud vultr object-info <subscription-id>   # Vultr Object Storage detail

# --- Monitoring ---
# alerts works on AWS (CloudWatch alarms), GCP / DO / Azure / OCI (alert policies).
# metrics works on AWS, GCP, DigitalOcean, Azure, and OCI.
spancloud monitor alerts aws                    # All CloudWatch alarms
spancloud monitor alerts aws --state ALARM      # Only firing alarms
spancloud monitor alerts gcp                    # GCP alert policies
spancloud monitor alerts digitalocean           # DO droplet alert policies
spancloud monitor alerts azure                  # Azure metric alerts
spancloud monitor alerts oci                    # OCI monitoring alarms

spancloud monitor metrics i-0abc123 --hours 3                 # AWS EC2 metrics (sparklines)
spancloud monitor metrics 12345 -p gcp --region us-central1-a # GCE metrics
```

All `cost show`, `audit run`, `unused scan`, `map show`, and `resource list`
commands accept any of the seven provider names, so the examples above with
`aws` swap in `gcp` / `vultr` / `digitalocean` / `azure` / `oci`
with identical flags.

```bash
# --- Configuration (CLI-side twin of the TUI Settings screen) ---

# Customize which resource types show up in the TUI sidebar for a provider
spancloud config sidebar aws --available              # List every available service
spancloud config sidebar aws --add ebs_volumes        # Add an extended service
spancloud config sidebar aws --remove lambda          # Remove one
spancloud config sidebar aws --reset                  # Back to defaults

# Enable/disable which providers show as TUI tabs
spancloud config providers                            # Current state

# --- Credential store management ---

spancloud auth store-info                             # macOS Keychain / Secret Service / file fallback
spancloud auth logout vultr                           # Forget stored Vultr key
spancloud auth logout digitalocean
```

### Run as a Python module

```bash
python -m spancloud --help
```

## Authentication

The easiest way to set up credentials is the interactive login:

```bash
spancloud auth login aws           # SSO (multi-account discovery), access keys, or profile selection
spancloud auth login gcp           # Sets up Application Default Credentials + project
spancloud auth login vultr         # API key setup and validation
spancloud auth login digitalocean  # Personal Access Token (saved to OS keychain)
spancloud auth login azure         # Wraps 'az login' + subscription picker
spancloud auth login oci           # Loads ~/.oci/config or runs 'oci setup config'
spancloud auth status              # Check all providers at a glance

# AWS multi-account profile management
spancloud profile list                          # List all configured AWS profiles
spancloud profile list --verify                 # Validate each via STS (shows account IDs)
spancloud profile show                          # Show current active profile identity
spancloud profile show production               # Inspect a specific profile

# --profile works on any command for multi-account access
spancloud resource list aws compute --profile production
spancloud cost show aws --profile staging
spancloud audit run aws --profile dev-account

# --gcp-project / -G switches the active GCP project for the run
# (overrides SPANCLOUD_GCP_PROJECT_ID and the ADC default)
spancloud --gcp-project my-other-proj cost show gcp
spancloud -G prod-analytics resource list gcp compute
```

Under the hood, Spancloud uses each provider's native credential chain:

### AWS
Uses the standard boto3 credential chain with a smart fallback:
- Environment variables (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`)
- Shared credentials file (`~/.aws/credentials`) — access-key profiles
- AWS Config file (`~/.aws/config`) — SSO profiles, assume-role profiles
- IAM roles (EC2 instance metadata, ECS task roles)

When the default chain doesn't produce working credentials and no
explicit profile was requested, Spancloud walks every configured
profile — SSO first, then access-keys, then assume-role — looking for
one that returns a valid STS response. This means a plain
`~/.aws/credentials` entry works out of the box; you don't need SSO
configured to use the TUI.

The CLI `spancloud auth login aws` flow detects your situation and
offers all four options: SSO login, SSO multi-account setup, access
keys, or switch to an existing profile.

### GCP
Uses Application Default Credentials:
- `gcloud auth application-default login`
- Service account key (`GOOGLE_APPLICATION_CREDENTIALS`)
- Workload Identity (GKE)
- Compute Engine metadata

### Vultr
Uses API key authentication:
- Environment variable (`SPANCLOUD_VULTR_API_KEY`)
- Interactive setup via `spancloud auth login vultr` — verified keys are
  saved to the OS keychain (macOS Keychain, Linux Secret Service, Windows
  Credential Locker) and reused on the next run
- Generate keys at: https://my.vultr.com/settings/#settingsapi

### DigitalOcean
Uses Personal Access Token authentication:
- Environment variable (`SPANCLOUD_DIGITALOCEAN_TOKEN`)
- Interactive setup via `spancloud auth login digitalocean` — tokens are
  saved to the OS keychain and reused on the next run
- Generate tokens at: https://cloud.digitalocean.com/account/api/tokens

### Azure
Uses the standard DefaultAzureCredential chain:
- Service-principal env vars (`AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET`, `AZURE_TENANT_ID`)
- Azure CLI (`az login`) — `spancloud auth login azure` wraps this plus subscription selection
- Managed Identity (when running in Azure)
- Subscription ID persisted to `~/.config/spancloud/azure.env`

### Oracle Cloud (OCI)
Uses the native OCI SDK config file:
- `~/.oci/config` with a selectable profile (defaults to `DEFAULT`)
- `spancloud auth login oci` lists existing profiles or shells out to `oci setup config` when none exists
- Chosen profile is persisted to `~/.config/spancloud/oci.env` for future runs
- Optional `SPANCLOUD_OCI_COMPARTMENT_ID` overrides the tenancy-root compartment

### Credential store

Vultr and DigitalOcean API keys are saved via the `keyring`
library, which writes to the OS-native secret store (macOS Keychain,
Linux Secret Service, Windows Credential Locker). On headless Linux or
in containers where no keyring backend is available, Spancloud falls
back to a Fernet-encrypted file at `~/.config/spancloud/credentials.enc`
with a mode-0600 key file alongside it.

AWS / GCP / Azure / OCI use their own native credential files
(`~/.aws`, ADC JSON, `az` CLI cache, `~/.oci/config`) and are not
touched by this store.

```bash
# Check which backend is in use
spancloud auth store-info

# Remove stored credentials for a provider
spancloud auth logout vultr
spancloud auth logout digitalocean
```

## Configuration

Spancloud reads configuration from environment variables prefixed with `SPANCLOUD_`:

| Variable | Default | Description |
|----------|---------|-------------|
| `SPANCLOUD_LOG_LEVEL` | `INFO` | Logging level |
| `SPANCLOUD_AWS_DEFAULT_REGION` | `us-east-1` | Default AWS region |
| `SPANCLOUD_AWS_PROFILE` | — | AWS CLI profile name |
| `SPANCLOUD_GCP_DEFAULT_REGION` | `us-central1` | Default GCP region |
| `SPANCLOUD_GCP_PROJECT_ID` | — | GCP project ID |
| `SPANCLOUD_VULTR_API_KEY` | — | Vultr API key (falls back to OS keychain) |
| `SPANCLOUD_DIGITALOCEAN_TOKEN` | — | DigitalOcean PAT (falls back to OS keychain) |
| `SPANCLOUD_AZURE_SUBSCRIPTION_ID` | — | Azure subscription ID |
| `SPANCLOUD_AZURE_TENANT_ID` | — | Azure tenant ID (optional) |
| `SPANCLOUD_OCI_CONFIG_FILE` | `~/.oci/config` | Path to OCI SDK config file |
| `SPANCLOUD_OCI_PROFILE` | `DEFAULT` | OCI config profile name |
| `SPANCLOUD_OCI_COMPARTMENT_ID` | — | Compartment OCID (defaults to tenancy root) |
| `SPANCLOUD_OCI_DEFAULT_REGION` | `us-ashburn-1` | Default OCI region |

## Project Structure

```
src/spancloud/
├── cli/                    # Typer-based CLI commands
│   ├── main.py             # Entry point and top-level commands
│   └── commands/           # Subcommand groups
│       ├── provider.py     # Provider management commands
│       ├── resource.py     # Resource discovery commands
│       ├── cost.py         # Cost analysis commands
│       ├── audit.py        # Security audit commands
│       ├── unused.py       # Unused resource detection
│       ├── map.py          # Resource relationship mapping
│       ├── monitor.py      # Monitoring alerts + metrics (AWS + GCP)
│       ├── s3.py           # S3 bucket detail viewer
│       ├── gcs.py          # GCS bucket detail viewer
│       ├── action.py       # Resource actions (AWS + GCP)
│       └── tui.py          # TUI launcher
├── tui/                    # Textual-based TUI
│   ├── app.py              # Main Textual application
│   ├── screens/
│   │   └── dashboard.py    # Tabbed dashboard (Overview + per-provider)
│   ├── widgets/
│   │   ├── overview_tab.py # Overview: all providers at a glance
│   │   ├── provider_tab.py # Per-provider: sidebar + resource table
│   │   ├── provider_panel.py # Legacy provider status card
│   │   └── resource_table.py # Legacy resource table
│   └── styles/
│       └── app.tcss        # Tabbed layout styles
├── analysis/               # Analysis features
│   └── models.py           # CostSummary, SecurityFinding, UnusedResource, etc.
├── core/                   # Core abstractions
│   ├── provider.py         # BaseProvider ABC
│   ├── resource.py         # Resource/ResourceType models
│   ├── registry.py         # Provider registry
│   └── exceptions.py       # Custom exceptions
├── providers/              # Cloud provider implementations
│   ├── aws/                # Amazon Web Services
│   │   ├── provider.py     # Main AWS provider
│   │   ├── auth.py         # Credential chain
│   │   ├── regions.py      # Multi-region discovery + parallel scanning
│   │   ├── resources.py    # EC2 instances, S3 buckets
│   │   ├── vpc.py          # VPCs, subnets, security groups
│   │   ├── rds.py          # RDS instances, Aurora clusters
│   │   ├── lambda_.py      # Lambda functions
│   │   ├── elb.py          # ALB, NLB, Classic load balancers
│   │   ├── eks.py          # EKS clusters, node groups, Fargate
│   │   ├── cost.py         # Cost Explorer analysis
│   │   ├── security.py     # Security audit checks
│   │   ├── unused.py       # Unused resource detection
│   │   ├── relationships.py # Resource relationship mapping
│   │   ├── cloudwatch.py   # CloudWatch alarms + metrics
│   │   ├── route53.py      # Route53 hosted zones + records
│   │   ├── s3_details.py   # Bucket policies, lifecycle, size
│   │   ├── iam.py          # Users, roles, policies
│   │   └── actions.py      # Start/stop/reboot/terminate EC2
│   ├── gcp/                # Google Cloud Platform
│   │   ├── provider.py     # Main GCP provider
│   │   ├── auth.py         # Application Default Credentials
│   │   ├── resources.py    # GCE instances, GCS buckets
│   │   ├── vpc.py          # VPC networks, subnets, firewall rules
│   │   ├── cloudsql.py     # Cloud SQL instances
│   │   ├── gke.py          # GKE clusters, node pools
│   │   ├── functions.py    # Cloud Functions (2nd gen)
│   │   ├── cloudrun.py     # Cloud Run services
│   │   ├── loadbalancer.py # Forwarding rules, backend services
│   │   ├── cost.py         # Cloud Billing + BigQuery cost analysis
│   │   ├── security.py     # Security audit checks
│   │   ├── unused.py       # Unused resource detection
│   │   ├── relationships.py # Resource relationship mapping
│   │   ├── monitoring.py   # Cloud Monitoring alerts + metrics
│   │   ├── dns.py          # Cloud DNS managed zones + records
│   │   ├── gcs_details.py  # Bucket IAM, lifecycle, size
│   │   └── actions.py      # Start/stop/reset GCE instances
│   ├── vultr/              # Vultr
│   │   ├── provider.py     # Main Vultr provider
│   │   ├── auth.py         # API key auth + REST client
│   │   ├── login.py        # Interactive API key login
│   │   ├── instances.py    # Cloud instances + bare metal
│   │   ├── storage.py      # Block + object storage
│   │   ├── vpc.py          # VPCs, firewall groups
│   │   ├── database.py     # Managed databases
│   │   ├── kubernetes.py   # VKE clusters + node pools
│   │   ├── loadbalancer.py # Load balancers
│   │   ├── dns.py          # DNS domains + records
│   │   ├── cost.py         # Billing API cost analysis
│   │   ├── security.py     # Security audit checks
│   │   ├── unused.py       # Unused resource detection
│   │   ├── relationships.py # Resource relationship mapping
│   │   └── actions.py      # Start/stop/reboot instances
│   ├── digitalocean/       # Droplets, Volumes, VPC, DOKS, DBs, LBs, DNS 
│   ├── azure/              # VMs, Blob Storage, VNet/NSG, AKS, SQL/Cosmos, App Service, LBs, DNS
│   ├── oci/                # Instances, Object Storage, VCN, ADB, OKE, LBs, DNS
│   └── alibaba/            # TODO: coming in a future release
├── config/                 # Configuration management
│   └── settings.py
└── utils/                  # Shared utilities
    ├── logging.py          # Rich-powered logging
    ├── retry.py            # Exponential backoff retry
    └── throttle.py         # Rate limiter for API calls
```

## Roadmap

All seven providers now have full feature parity across resource discovery,
cost, audit, unused detection, relationships, monitoring alerts, and
lifecycle actions. The matrix below captures the current state:

|              | resources | cost | audit | unused | relationships | alerts | actions | serverless | metrics |
|--------------|:---------:|:----:|:-----:|:------:|:-------------:|:------:|:-------:|:----------:|:-------:|
| AWS          |    ✓      |  ✓   |   ✓   |   ✓    |       ✓       |   ✓    |    ✓    |     ✓      |    ✓    |
| GCP          |    ✓      |  ✓   |   ✓   |   ✓    |       ✓       |   ✓    |    ✓    |     ✓      |    ✓    |
| Azure        |    ✓      |  ✓   |   ✓   |   ✓    |       ✓       |   ✓    |    ✓    |     ✓      |    ✓    |
| DigitalOcean |    ✓      |  ✓*  |   ✓   |   ✓    |       ✓       |   ✓    |    ✓    |     ✓      |    ✓    |
| Vultr        |    ✓      |  ✓   |   ✓   |   ✓    |       ✓       |   —**  |    ✓    |     —      |    —    |
| OCI          |    ✓      |  ✓   |   ✓   |   ✓    |       ✓       |   ✓    |    ✓    |     ✓      |    ✓    |
| Alibaba      |   TODO    |      |       |        |               |        |         |            |         |

\* DO cost requires an account with the **Billing** team role — full-access PATs on a Member account return 403.
\** Vultr has no public alerts API; monitoring is dashboard-only.

Per-provider resource coverage highlights:
- **AWS:** EC2, EBS, S3, VPC/Subnet/SG, RDS/Aurora, Lambda, ALB/NLB/CLB, EKS, Route53, IAM, CloudWatch, Cost Explorer
- **GCP:** GCE, GCS, VPC/Subnet/Firewall, Cloud SQL, Cloud Functions, Cloud Run, GKE, Load Balancers, Cloud DNS, Cloud Monitoring, Billing API
- **Azure:** VMs, Blob Storage, VNet/Subnet/NSG/Public IP, Azure SQL + Cosmos DB, App Service + Functions, AKS, Load Balancers, DNS, Azure Monitor, Cost Management
- **DigitalOcean:** Droplets, Volumes, Spaces CDN, VPCs, Firewalls, Managed DBs, DOKS, Load Balancers, DNS, App Platform (serverless apps), Functions, Monitoring Alerts, Balance / Billing History
- **Vultr:** Instances + Bare Metal, Block + Object Storage, VPCs, Firewalls, Managed DBs, VKE, Load Balancers, DNS, Billing History
- **OCI:** Compute Instances, Object Storage + Block Volumes, VCN/Subnet/Security List/NSG, Autonomous DB + DB Systems, OKE, Oracle Functions, LB + NLB, DNS Zones, Monitoring Alarms, Usage API
- **Alibaba Cloud:** Coming in a future release

### Next up

- [ ] **IAM for GCP** — Service accounts, custom roles, workload identity pools
- [ ] **IAM for Azure** — RBAC role assignments, managed identities, app registrations
- [ ] **Resource diffing** — Snapshot + compare "what changed since" per provider
- [ ] **Tag compliance** — Find resources missing required tags
- [ ] **Cross-provider search** — Query `"prod-*"` across every authed provider in parallel
- [ ] **Notifications / scheduled scans** — Cron-style monitoring with Slack/email alerts
- [ ] **Vultr monitoring** — Only if/when Vultr publishes a public alerts API
- [ ] **Additional Azure monitoring types** — Activity-log + scheduled-query alerts (currently metric alerts only)
## Development

```bash
# Clone and install in editable mode with dev + GUI deps
git clone https://github.com/daytonjones/spancloud.git
cd spancloud
pip install -e ".[dev]"

# Run tests
pytest

# Lint
ruff check src/ tests/

# Type check
mypy src/
```

