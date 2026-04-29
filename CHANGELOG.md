# Changelog

All notable changes to spancloud are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

---

## [Unreleased]

---

## [0.1.6] — 2026-04-30

### Added
- GUI: Monitoring Alerts panel now fetches live data (AWS CloudWatch, GCP, Azure, DO, OCI); was previously a hardcoded stub
- GUI: GCP auth dialog shows project picker when multiple projects exist; auto-selects if only one; manual text entry fallback when listing fails
- GUI: Quit button (✕) in toolbar and `Ctrl+Q` shortcut
- GUI: Tag filter input (`🏷 tag:key=value`) alongside text search — AND logic for multiple pairs
- GUI: OCI Monitoring metrics panel explains the Monitoring plugin requirement when data is empty
- TUI: `tag:key=value` filter syntax in search bar (can mix with text: `web tag:env=prod`)
- TUI: Global App Settings screen (`S` key) — provider enable/disable and theme selection (9 built-in Textual themes, persisted across sessions)
- TUI: OCI profile name shown in sidebar status label after auth
- TUI: Azure subscription picker in sidebar
- TUI: GCP org selector now filters project list correctly
- TUI: Monitoring Alerts fetches real data for all providers (was already implemented; now matches GUI)
- GCP: project read from `gcloud config` when ADC doesn't carry one; quota project auto-set after selection to prevent API-not-enabled errors
- GCP: BigQuery billing export dataset auto-discovered by scanning all datasets (no longer requires a specific dataset name)
- GCP: `PERMISSION_DENIED` 403 errors mapped to specific IAM role guidance per service (Compute, BigQuery, Cloud Billing, etc.)
- GCP: GCE metadata server timeout warnings suppressed on non-GCE machines
- OCI: 401/404 treated as permanent errors (no retries); single concise warning per session instead of one per resource type
- OCI: `verify()` now actually validates credentials — no longer silently succeeds with an expired API key
- CLI: `spancloud permissions [provider]` — print required IAM roles per provider
- CLI: `spancloud about` — version, providers, license, links
- CLI: `spancloud status` — authentication status table for all providers
- Shell completion: `spancloud --install-completion` (bash, zsh, fish) — documented in README Installation section
- Startup version check: GUI (amber status bar) and TUI (15 s notify banner) alert when a newer PyPI release is available
- Retry log messages now include provider name (`azure :: get_cost_summary`) instead of bare function name
- CI/CD: GitHub Actions workflow auto-tags, builds, and publishes to PyPI on every merge to main
- CHANGELOG.md added to repository

### Fixed
- TUI App Settings crash: two widgets shared `id="section-label"`; Textual requires unique IDs
- GCP org project filter in TUI was referencing non-existent `auth._cached_projects`; projects now cached on the sidebar widget
- `spancloud status` crashed with `AttributeError: 'ProviderRegistry' has no attribute 'all'`
- `google.auth` quota-project `UserWarning` suppressed (was printed on every GCP API call)
- OCI error messages no longer dump full multi-line dict; show concise `status | code | message`
- README: "seven providers" corrected to "six implemented providers" throughout; Alibaba removed from CLI help text

---

## [0.1.5] — 2026-04-29

### Added
- GUI: Right-click context menu on resource table — Copy Name, Copy ID, Open in Cloud Console (per-provider deep links for AWS, GCP, Azure, DO, Vultr, OCI)
- GUI: `Ctrl+E` keyboard shortcut for export (same as clicking ⬇ Export)
- GUI: Tag filter input (`🏷 tag:key=value`) in search bar alongside text search
- GUI: Indeterminate progress bar during resource loading
- TUI: Export success notification now shows full resolved file path
- OCI provider: profile selector in GUI and TUI sidebars
- Azure: subscription picker in TUI sidebar (mirrors GUI)
- GCP: org selector in TUI; project list fetched once per session to avoid 429 rate limits
- CLI metrics: added DigitalOcean, Azure, OCI support (`spancloud monitor metrics --provider digitalocean/azure/oci`)
- `google-cloud-bigquery` added to declared dependencies (was installed but undeclared)
- `shellingham` added to declared dependencies (required for `--install-completion`)

### Fixed
- DigitalOcean load balancer `metadata.size` was an `int`; caused pydantic validation failure and repeated retry warnings
- Auth guard: clicking nav items while unauthenticated no longer triggers API calls
- GCP project change in TUI caused infinite notification loop; fixed with direct status label update instead of re-running `_check_auth()`
- `asyncio` event loop rebinding errors in `RateLimiter` across `AsyncWorker` thread boundaries
- GUI overview card grid gaps when providers are disabled; fixed `isHidden()` vs `isVisible()` logic
- Vultr `$250` promotional credit was counted as a charge
- Vultr `/blocks` 502 error no longer kills VPC+firewall relationship mapping
- Vultr VPC endpoint corrected (`/vpc2`, key `vpc2_networks`); VPC 1.0 fallback added via subnet matching

---

## [0.1.4] — 2026-04-28

### Added
- GUI: Resource export — ⬇ Export button in resource table toolbar writes JSON, CSV, or YAML via native file dialog
- GUI: GCP Cloud Monitoring metrics for compute instances
- GUI: Azure Monitor metrics for virtual machines
- GUI: DigitalOcean Monitoring metrics (CPU, memory, bandwidth, disk)
- GUI: Vultr bandwidth metrics (daily totals, last 14 days)
- GUI: OCI Monitoring metrics for compute instances
- GUI: Relationship maps wired to real provider APIs for all providers
- TUI: About keybinding (`a`) — shows version, providers, license, links
- TUI: GCP org selector + project list with 429-guard (fetched once per auth)
- GUI: GCP org selector in provider controls (hidden unless ≥2 orgs)

### Fixed
- Azure auth crash with `azure-mgmt-subscription` v3.x
- Azure cost query with timezone-aware datetimes; 429 backoff extended
- Azure permanent API errors (subscription not found) no longer retried
- GCP `accessNotConfigured` 403 — skip retries, show enable URL
- GCP quota errors show friendly message pointing to GCP Console
- GUI startup flash-and-exit on Linux (delayed auth checks)
- GUI loading indicator on overview cards while resource count fetches

---

## [0.1.3] — 2026-04-26

### Added
- GUI: GCP project selector in provider controls sidebar
- GUI: Azure subscription picker in provider controls sidebar
- GUI: Provider enable/disable checkboxes in Settings dialog
- GUI: Theme switcher in Settings dialog (Tokyo Night, Dark, Dracula, Solarized Dark, Light)
- GUI: Relationship panel wired to real provider APIs
- AWS metrics expanded: RDS, Lambda, ALB/NLB/CLB; non-metric types explained
- GCP: friendly error messages for API-disabled and quota exceeded

### Fixed
- GUI mock mode showing real AWS profiles, GCP projects, Azure subscriptions
- GCP API-disabled (accessNotConfigured) 403 no longer retried

---

## [0.1.2] — 2026-04-24

### Changed
- Alibaba Cloud provider disabled pending multi-account profile support; marked "Coming Soon"
- `pyproject.toml`: alibabacloud-* and oss2 dependencies commented out
- README: "seven providers" corrected to "six implemented providers" throughout

### Fixed
- `pyproject.toml` classifiers, description, and keywords updated to reflect all 7 target providers
- PySide6 moved to main dependencies (was missing); `pip install spancloud` now includes GUI

---

## [0.1.1] — 2026-04-23

### Added
- Desktop GUI (PySide6/Qt6) as default interface (`spancloud` launches GUI; `--tui` for TUI)
- `--mock` demo mode for GUI and TUI — realistic sample data, no credentials needed
- Screenshots in README (`docs/screenshots/`)
- `sc` short alias entry point
- GitHub repository made public

### Fixed
- `--mock` mode was reading real AWS profiles, GCP projects, Azure subscriptions — replaced with generic demo data
- GCP project key in mock data (`projectId` → `project_id`)
- Screenshot URLs use `raw.githubusercontent.com` for reliable rendering on PyPI
- `pyproject.toml` version mismatch with `__init__.py`

---

## [0.1.0] — 2026-04-21

Initial release.

### Features
- **Seven cloud providers** (six fully implemented): AWS, GCP, Azure, DigitalOcean, Vultr, OCI, Alibaba Cloud
- **Desktop GUI** (PySide6/Qt6) — provider sidebar, overview dashboard, resource table with sort/filter, detail drawer, analysis panels
- **TUI** (Textual) — tabbed dashboard, per-provider sidebar, resource table, analysis panels
- **CLI** (Typer) — `resource list/show`, `cost show`, `audit run`, `unused scan`, `map show`, `monitor alerts/metrics`, `action start/stop/reboot`, `auth login/status/logout`
- **Resource discovery**: EC2, S3, VPC, RDS, Lambda, ELB, EKS, Route53, IAM (AWS); GCE, GCS, CloudSQL, GKE, Cloud Functions, Cloud Run, LBs, Cloud DNS (GCP); VMs, Blob, VNet, SQL, Cosmos, AKS, App Service, DNS (Azure); Droplets, Volumes, Spaces, DOKS, Managed DBs (DO); Instances, Block/Object Storage, VPCs, VKE, Managed DBs (Vultr); Instances, Object Storage, VCN, ADB, OKE, LBs, DNS (OCI)
- **Analysis**: cost summary, security audit, unused resource detection, relationship mapping, monitoring alerts, instance metrics
- **AWS multi-region scanning** (`--all-regions`)
- **Tag filtering** with AND logic (`--tag key=val`)
- **Export** to JSON, CSV, YAML
- **Credential storage**: OS keychain (macOS Keychain, Linux Secret Service) with encrypted file fallback
- **Retry with exponential backoff** for all cloud API calls
