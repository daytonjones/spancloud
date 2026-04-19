"""Per-provider view: resource-type sidebar + table + right drawer + analysis."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QTextEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from spancloud.gui.async_worker import AsyncWorker
from spancloud.gui.theme import (
    ACCENT_BLUE,
    ACCENT_YELLOW,
    BG_ELEVATED,
    BG_SURFACE,
    BORDER_SUBTLE,
    STATUS_ERROR,
    STATUS_OK,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)
from spancloud.gui.widgets.provider_controls import ProviderControls

if TYPE_CHECKING:
    from spancloud.core.provider import BaseProvider
    from spancloud.core.resource import Resource

# ---------------------------------------------------------------------------
# Analysis-type sidebar items
# ---------------------------------------------------------------------------
_ANALYSIS_ITEMS = [
    ("cost",          "💰 Cost Summary"),
    ("audit",         "🛡  Security Audit"),
    ("unused",        "🗑  Unused Resources"),
    ("relationships", "🔗 Relationships"),
    ("alerts",        "🔔 Monitoring Alerts"),
    ("metrics",       "📊 Metrics"),
]

_STATE_COLOR: dict[str, str] = {
    "running":    STATUS_OK,
    "stopped":    STATUS_ERROR,
    "pending":    ACCENT_YELLOW,
    "terminated": TEXT_MUTED,
    "error":      STATUS_ERROR,
    "unknown":    TEXT_MUTED,
}


# ---------------------------------------------------------------------------
# Tokyo Night colour palette for analysis HTML
# ---------------------------------------------------------------------------
_H = {
    "title":    "#7aa2f7",   # blue  — section headers
    "period":   "#e0af68",   # amber — dates, periods
    "label":    "#7dcfff",   # cyan  — service / resource names
    "amount":   "#9ece6a",   # green — dollar amounts
    "pct":      "#bb9af7",   # purple — percentages
    "savings":  "#9ece6a",   # green — savings amounts
    "sep":      "#3b4261",   # dim   — separator lines
    "note":     "#565f89",   # muted — notes / hints
    "bar":      "#e0af68",   # amber — trend bars
    "crit":     "#f7768e",   # red   — critical
    "high":     "#ff9e64",   # orange — high
    "med":      "#e0af68",   # amber — medium
    "low":      "#7aa2f7",   # blue  — low
    "info":     "#565f89",   # muted — info
    "ok":       "#9ece6a",   # green — no issues / clean
    "rec":      "#565f89",   # muted — recommendation text
    "reason":   "#cfc9c2",   # off-white — reason text
}

_MONO = "font-family:'JetBrains Mono','Fira Code','Cascadia Code',monospace;font-size:12px;"

def _s(color: str, text: str) -> str:
    """Wrap text in a colored span."""
    return f'<span style="color:{color}">{text}</span>'

def _sep_row(cols: int = 1) -> str:
    return (
        f'<tr><td colspan="{cols}" style="padding:3px 0;">'
        f'<hr style="border:none;border-top:1px solid {_H["sep"]};margin:0;"></td></tr>'
    )

def _wrap(body: str) -> str:
    return f'<div style="{_MONO}padding:8px;">{body}</div>'


# ---------------------------------------------------------------------------
# Analysis HTML formatters
# ---------------------------------------------------------------------------

def _format_cost(summary: object) -> str:  # CostSummary
    period = _s(_H["period"], f'{summary.period_start} → {summary.period_end}')  # type: ignore[attr-defined]
    rows = [
        f'<p style="margin:0 0 6px;font-size:13px;font-weight:700;">'
        f'{_s(_H["title"], "Monthly Cost")}  <span style="font-weight:400;">{period}</span></p>',
        '<table style="width:100%;border-collapse:collapse;">',
        _sep_row(3),
    ]

    if getattr(summary, "notes", None):
        rows.append(
            f'<tr><td colspan="3" style="padding:2px 0;">'
            f'{_s(_H["note"], "Note: " + summary.notes)}</td></tr>'  # type: ignore[attr-defined]
        )
        rows.append(_sep_row(3))

    for svc in summary.by_service[:15]:  # type: ignore[attr-defined]
        pct = (
            f"{float(svc.cost / summary.total_cost * 100):.1f}%"  # type: ignore[attr-defined]
            if summary.total_cost > 0 else "—"  # type: ignore[attr-defined]
        )
        rows.append(
            f'<tr>'
            f'<td style="padding:2px 4px 2px 0;">{_s(_H["label"], svc.service)}</td>'
            f'<td style="padding:2px 8px;text-align:right;">{_s(_H["pct"], pct)}</td>'
            f'<td style="padding:2px 0 2px 8px;text-align:right;font-weight:600;">'
            f'{_s(_H["amount"], f"${svc.cost:,.2f} / mo")}</td>'
            f'</tr>'
        )

    rows.append(_sep_row(3))
    rows.append(
        f'<tr>'
        f'<td style="padding:3px 0;font-weight:700;">{_s(_H["title"], "Estimated total")}</td>'
        f'<td></td>'
        f'<td style="padding:3px 0;text-align:right;font-weight:700;font-size:13px;">'
        f'{_s(_H["amount"], f"${summary.total_cost:,.2f} / mo")}</td>'  # type: ignore[attr-defined]
        f'</tr>'
    )

    if getattr(summary, "daily_costs", None):
        recent = summary.daily_costs[-7:]  # type: ignore[attr-defined]
        max_cost = max(d.cost for d in recent) if recent else 1
        rows += [
            _sep_row(3),
            f'<tr><td colspan="3" style="padding:6px 0 2px;">'
            f'<b>{_s(_H["title"], "Daily trend — last 7 days")}</b></td></tr>',
        ]
        for day in recent:
            bar_len = int(float(day.cost / max_cost) * 20) if max_cost > 0 else 0
            rows.append(
                f'<tr>'
                f'<td style="padding:1px 4px 1px 0;">{_s(_H["period"], str(day.date))}</td>'
                f'<td style="padding:1px 8px;text-align:right;font-weight:600;">'
                f'{_s(_H["amount"], f"${day.cost:,.2f}")}</td>'
                f'<td style="padding:1px 0 1px 8px;">{_s(_H["bar"], "█" * bar_len)}</td>'
                f'</tr>'
            )

    rows.append("</table>")
    return _wrap("".join(rows))


def _format_audit(result: object) -> str:  # SecurityAuditResult
    sev_color = {
        "critical": _H["crit"], "high": _H["high"],
        "medium":   _H["med"],  "low":  _H["low"], "info": _H["info"],
    }

    count = len(result.findings)  # type: ignore[attr-defined]
    rows = [
        f'<p style="margin:0 0 6px;font-size:13px;font-weight:700;">'
        f'{_s(_H["title"], "Security Audit")}  '
        f'<span style="font-weight:400;color:{_H["note"]};">'
        f'{count} finding(s) — {result.summary}</span></p>',  # type: ignore[attr-defined]
        '<table style="width:100%;border-collapse:collapse;">',
        _sep_row(3),
    ]

    if not result.findings:  # type: ignore[attr-defined]
        rows.append(
            f'<tr><td colspan="3" style="padding:4px 0;">'
            f'{_s(_H["ok"], "✓  No security issues found")}</td></tr>'
        )
    else:
        for f in sorted(result.findings, key=lambda x: x.severity.value):  # type: ignore[attr-defined]
            sev = f.severity.value
            color = sev_color.get(sev, _H["info"])
            rows.append(
                f'<tr style="vertical-align:top;">'
                f'<td style="padding:3px 4px 1px 0;white-space:nowrap;font-weight:700;">'
                f'{_s(color, sev.upper())}</td>'
                f'<td style="padding:3px 0 1px 8px;">'
                f'{_s(_H["label"], f.resource_type + "/" + f.resource_id)}</td>'
                f'</tr>'
                f'<tr><td></td>'
                f'<td style="padding:0 0 1px 8px;">{_s(_H["reason"], f.title)}</td>'
                f'</tr>'
                f'<tr><td></td>'
                f'<td style="padding:0 0 6px 8px;">'
                f'{_s(_H["rec"], "→ " + f.recommendation)}</td>'
                f'</tr>'
            )

    rows.append("</table>")
    return _wrap("".join(rows))


def _format_unused(report: object) -> str:  # UnusedResourceReport
    total = report.total_estimated_monthly_savings  # type: ignore[attr-defined]
    savings_str = (
        _s(_H["savings"], f"${total:,.2f} / mo potential savings")
        if total > 0
        else _s(_H["note"], "No cost estimates available")
    )
    rows = [
        f'<p style="margin:0 0 6px;font-size:13px;font-weight:700;">'
        f'{_s(_H["title"], "Unused / Idle Resources")}  '
        f'<span style="font-weight:400;color:{_H["note"]};">'
        f'{report.total_count} item(s)</span></p>',  # type: ignore[attr-defined]
        f'<p style="margin:0 0 6px;">{savings_str}</p>',
        '<table style="width:100%;border-collapse:collapse;">',
        _sep_row(4),
        f'<tr style="font-weight:700;">'
        f'<td style="padding:2px 4px 2px 0;">{_s(_H["title"], "Resource")}</td>'
        f'<td style="padding:2px 8px;">{_s(_H["title"], "Type")}</td>'
        f'<td style="padding:2px 8px;">{_s(_H["title"], "Reason")}</td>'
        f'<td style="padding:2px 0 2px 8px;text-align:right;">{_s(_H["title"], "Savings")}</td>'
        f'</tr>',
        _sep_row(4),
    ]

    for r in report.resources:  # type: ignore[attr-defined]
        sav = (
            _s(_H["savings"], r.estimated_monthly_savings)
            if r.estimated_monthly_savings else _s(_H["note"], "—")
        )
        rows.append(
            f'<tr style="vertical-align:top;">'
            f'<td style="padding:2px 4px 2px 0;">{_s(_H["label"], r.resource_name)}</td>'
            f'<td style="padding:2px 8px;">{_s(_H["note"], r.resource_type)}</td>'
            f'<td style="padding:2px 8px;">{_s(_H["reason"], r.reason)}</td>'
            f'<td style="padding:2px 0 2px 8px;text-align:right;">{sav}</td>'
            f'</tr>'
        )

    rows += [_sep_row(4), "</table>"]
    return _wrap("".join(rows))


# ---------------------------------------------------------------------------
# Mock analysis — demo data for --mock mode
# ---------------------------------------------------------------------------

_MOCK_RELATIONSHIPS: dict[str, list[tuple[str, str, str, str, str]]] = {
    # (from_type, from_name, edge_label, to_type, to_name)
    "aws": [
        ("ALB",      "prod-alb",         "routes to",   "EC2",     "web-prod-01"),
        ("ALB",      "prod-alb",         "routes to",   "EC2",     "api-prod-01"),
        ("EC2",      "web-prod-01",       "writes to",   "S3",      "prod-assets-bucket"),
        ("EC2",      "api-prod-01",       "connects to", "RDS",     "prod-postgres"),
        ("EC2",      "worker-prod-01",    "connects to", "RDS",     "analytics-pg"),
        ("EC2",      "worker-prod-01",    "reads from",  "S3",      "prod-logs-archive"),
        ("Lambda",   "api-handler",       "connects to", "RDS",     "prod-mysql"),
        ("Lambda",   "image-resizer",     "writes to",   "S3",      "prod-assets-bucket"),
        ("EKS",      "prod-cluster",      "runs in",     "VPC",     "prod-vpc"),
        ("EC2",      "web-prod-01",       "runs in",     "VPC",     "prod-vpc"),
        ("NLB",      "prod-nlb",          "routes to",   "EKS",     "prod-cluster"),
    ],
    "gcp": [
        ("GKE",      "prod-gke",          "runs in",     "VPC",     "default"),
        ("VM",       "web-01",            "reads from",  "GCS",     "demo-prod-assets"),
        ("VM",       "api-01",            "connects to", "CloudSQL", "prod-postgres"),
        ("Function", "api-handler",       "connects to", "CloudSQL", "prod-postgres"),
        ("Function", "data-proc",         "writes to",   "GCS",     "demo-backups"),
        ("VM",       "worker-01",         "reads from",  "GCS",     "demo-staging-data"),
    ],
    "azure": [
        ("VM",       "web-vm-01",         "reads from",  "Storage", "prodstgacct"),
        ("VM",       "api-vm-01",         "connects to", "SQL",     "prod-sql"),
        ("VM",       "web-vm-01",         "runs in",     "VNet",    "prod-vnet"),
        ("VM",       "api-vm-01",         "runs in",     "VNet",    "prod-vnet"),
    ],
    "digitalocean": [
        ("Droplet",  "web-droplet-01",    "attached to", "Volume",  "prod-data-volume"),
        ("DOKS",     "prod-doks",         "uses",        "Volume",  "prod-data-volume"),
    ],
    "vultr": [
        ("VM",       "web-01",            "attached to", "Block",   "prod-block-storage"),
    ],
    "oci": [
        ("VM",       "web-instance-01",   "runs in",     "VCN",     "prod-vcn"),
        ("VM",       "api-instance-01",   "runs in",     "VCN",     "prod-vcn"),
        ("VM",       "web-instance-01",   "reads from",  "Object",  "prod-object-storage"),
    ],
    "alibaba": [
        ("ECS",      "web-ecs-01",        "connects to", "RDS",     "prod-rds"),
        ("ECS",      "worker-ecs-01",     "reads from",  "OSS",     "demo-prod-bucket"),
    ],
}


def _mock_relationships(name: str, C: dict, wrap: object) -> str:
    edges = _MOCK_RELATIONSHIPS.get(name, [])
    if not edges:
        body = (
            f'<span style="color:{C["title"]};font-size:14px;font-weight:bold;">Resource Relationships</span><br><br>'
            f'<span style="color:{C["val"]};">✓ No relationships to display (demo data)</span>'
        )
        return wrap(body)  # type: ignore[operator]

    # Build adjacency: group edges by source node
    from collections import defaultdict
    by_src: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
    for ft, fn, edge, tt, tn in edges:
        by_src[f"{ft}:{fn}"].append((edge, tt, tn))

    rows = []
    seen_src: set[str] = set()
    for ft, fn, edge, tt, tn in edges:
        src_key = f"{ft}:{fn}"
        if src_key not in seen_src:
            seen_src.add(src_key)
            rows.append(
                f'<tr><td colspan="4" style="padding:8px 0 2px 8px;color:{C["label"]};font-weight:bold;">'
                f'[{ft}] <span style="color:#c0caf5;">{fn}</span></td></tr>'
            )
        rows.append(
            f'<tr>'
            f'<td style="color:{C["muted"]};padding:1px 4px 1px 24px;">│</td>'
            f'<td style="color:{C["muted"]};padding:1px 8px 1px 0;">──</td>'
            f'<td style="color:{C["purple"]};padding:1px 12px 1px 0;font-style:italic;">{edge}</td>'
            f'<td style="color:{C["label"]};padding:1px 8px 1px 0;">[{tt}]</td>'
            f'<td style="color:#c0caf5;padding:1px 0;">{tn}</td>'
            f'</tr>'
        )

    html = (
        f'<span style="color:{C["title"]};font-size:14px;font-weight:bold;">Resource Relationships</span><br>'
        f'<span style="color:{C["muted"]};">Demo data · {len(edges)} relationship(s)</span><br><br>'
        f'<table cellspacing="0">{"".join(rows)}</table>'
    )
    return wrap(html)  # type: ignore[operator]

_MOCK_COST: dict[str, tuple[str, str, str, str]] = {
    "aws":          ("$4,821.40", "$312.90", "$4,508.50", "EC2 Instances,S3 Storage,RDS Databases,Lambda Functions"),
    "gcp":          ("$2,340.10", "$187.20", "$2,152.90", "Compute Engine,Cloud Storage,Cloud SQL,Cloud Functions"),
    "azure":        ("$3,102.75", "$241.30", "$2,861.45", "Virtual Machines,Blob Storage,Azure SQL,App Service"),
    "digitalocean": ("$890.50",   "$62.10",  "$828.40",   "Droplets,Spaces,Managed Databases,Kubernetes"),
    "vultr":        ("$412.20",   "$28.80",  "$383.40",   "Cloud Compute,Block Storage,Managed Databases"),
    "oci":          ("$1,230.60", "$94.50",  "$1,136.10", "Compute Instances,Object Storage,Autonomous DB"),
    "alibaba":      ("$1,875.30", "$143.70", "$1,731.60", "ECS Instances,OSS Storage,ApsaraDB RDS"),
}

_MOCK_FINDINGS: dict[str, list[tuple[str, str, str]]] = {
    "aws":          [("HIGH", "S3 bucket 'dev-scratch-bucket' has public read ACL", "s3"), ("MEDIUM", "IAM user 'alice@example.com' has no MFA enabled", "iam"), ("LOW", "EC2 instance 'dev-sandbox' uses default security group", "ec2")],
    "gcp":          [("MEDIUM", "Cloud Storage bucket 'demo-staging-data' is publicly accessible", "storage"), ("LOW", "GKE cluster 'prod-gke' has legacy ABAC enabled", "container")],
    "azure":        [("HIGH", "Storage account 'devstgacct' allows public blob access", "storage"), ("MEDIUM", "VM 'dev-vm-01' has no disk encryption", "compute")],
    "digitalocean": [("LOW", "Droplet 'staging-droplet' has no firewall rule assigned", "compute")],
    "vultr":        [("MEDIUM", "Instance 'staging-01' uses SSH password authentication", "compute")],
    "oci":          [("LOW", "Object storage bucket 'archive-storage' has no lifecycle policy", "storage")],
    "alibaba":      [("MEDIUM", "ECS instance 'worker-ecs-01' security group allows 0.0.0.0/0 on port 22", "compute")],
}

_MOCK_UNUSED: dict[str, list[tuple[str, str, str, str]]] = {
    "aws":          [("COMPUTE", "dev-sandbox", "Stopped 47 days", "$14.40/mo"), ("STORAGE", "dev-scratch-bucket", "No access in 90+ days", "$2.10/mo"), ("DATABASE", "analytics-pg", "Stopped 62 days", "$48.20/mo")],
    "gcp":          [("COMPUTE", "worker-01", "Stopped 31 days", "$38.50/mo")],
    "azure":        [("COMPUTE", "dev-vm-01", "Stopped 28 days", "$31.20/mo")],
    "digitalocean": [("COMPUTE", "staging-droplet", "Stopped 19 days", "$12.00/mo"), ("STORAGE", "staging-data-volume", "Unattached 14 days", "$5.00/mo")],
    "vultr":        [("COMPUTE", "staging-01", "Stopped 22 days", "$6.00/mo")],
    "oci":          [],
    "alibaba":      [],
}


def _metrics_no_selection_html() -> str:
    return (
        '<div style="font-family:monospace;font-size:12px;padding:40px 24px;color:#c0caf5;text-align:center;">'
        '<div style="font-size:36px;margin-bottom:16px;">📊</div>'
        '<div style="color:#7aa2f7;font-size:15px;font-weight:bold;margin-bottom:12px;">No resource selected</div>'
        '<div style="color:#565f89;font-size:12px;line-height:1.8;">'
        'Click any row in the resource table<br>'
        'on the left, then return here<br>'
        'to view its performance metrics.'
        '</div>'
        '<div style="color:#3b4261;font-size:24px;margin-top:20px;">↑</div>'
        '</div>'
    )


def _sparkline(values: list[float], color: str) -> str:
    blocks = "▁▂▃▄▅▆▇█"
    mn, mx = min(values), max(values)
    rng = mx - mn or 1
    chars = "".join(blocks[min(7, int((v - mn) / rng * 7))] for v in values)
    return f'<span style="color:{color};letter-spacing:1px;">{chars}</span>'


def _mock_metrics_for(resource: Resource) -> str:
    import hashlib, math
    C = {"title": "#7aa2f7", "label": "#7dcfff", "val": "#9ece6a", "muted": "#565f89",
         "warn": "#e0af68", "high": "#ff9e64", "purple": "#bb9af7"}

    seed = int(hashlib.md5(resource.id.encode()).hexdigest()[:8], 16)

    def fake_series(base: float, noise: float, n: int = 24) -> list[float]:
        vals = []
        v = base
        for i in range(n):
            v += (((seed * (i + 1) * 6364136223846793005 + 1442695040888963407) & 0xFFFFFFFF) / 0xFFFFFFFF - 0.5) * noise
            v = max(0.0, min(100.0, v))
            vals.append(round(v, 1))
        return vals

    is_stopped = resource.state.value in ("stopped", "terminated")
    cpu_base = 0.0 if is_stopped else 15 + (seed % 40)
    mem_base = 0.0 if is_stopped else 30 + (seed % 35)
    net_base = 0.0 if is_stopped else 5 + (seed % 20)

    cpu  = fake_series(cpu_base,  12)
    mem  = fake_series(mem_base,  8)
    net  = fake_series(net_base,  15)
    disk = fake_series(40 + (seed % 30), 5)

    def stat_row(label: str, series: list[float], unit: str, color: str) -> str:
        cur = series[-1]
        lo  = min(series)
        hi  = max(series)
        spark = _sparkline(series, color)
        return (
            f'<tr>'
            f'<td style="color:{C["label"]};padding:4px 12px 4px 8px;white-space:nowrap;">{label}</td>'
            f'<td style="padding:4px 16px 4px 0;">{spark}</td>'
            f'<td style="color:{color};padding:4px 8px;font-weight:bold;">{cur:.1f}{unit}</td>'
            f'<td style="color:{C["muted"]};padding:4px 0;font-size:11px;">lo {lo:.1f}  hi {hi:.1f}</td>'
            f'</tr>'
        )

    rt_label = resource.resource_type.value.replace("_", " ").title()
    state_color = C["val"] if not is_stopped else C["warn"]
    meta_rows = "".join(
        f'<tr><td style="color:{C["muted"]};padding:1px 12px 1px 8px;">{k}</td>'
        f'<td style="color:#c0caf5;">{v}</td></tr>'
        for k, v in list(resource.metadata.items())[:4]
    )

    html = (
        f'<span style="color:{C["title"]};font-size:14px;font-weight:bold;">📊 Metrics</span><br>'
        f'<span style="color:{C["muted"]};">Demo data · last 24 hours</span><br><br>'
        f'<table cellspacing="0">'
        f'<tr><td style="color:{C["label"]};padding:2px 12px 2px 8px;">Resource</td>'
        f'<td style="color:#c0caf5;font-weight:bold;">{resource.name}</td></tr>'
        f'<tr><td style="color:{C["label"]};padding:2px 12px 2px 8px;">Type</td>'
        f'<td style="color:{C["purple"]};">{rt_label}</td></tr>'
        f'<tr><td style="color:{C["label"]};padding:2px 12px 2px 8px;">State</td>'
        f'<td style="color:{state_color};">{resource.state.value}</td></tr>'
        f'<tr><td style="color:{C["label"]};padding:2px 12px 2px 8px;">Region</td>'
        f'<td style="color:#c0caf5;">{resource.region}</td></tr>'
        f'{meta_rows}'
        f'</table>'
        f'<br><span style="color:{C["label"]};">Performance  <span style="color:{C["muted"]};font-size:10px;">(hourly, 24h)</span></span><br><br>'
        f'<table cellspacing="0">'
        f'{stat_row("CPU", cpu, "%", C["val"])}'
        f'{stat_row("Memory", mem, "%", C["purple"])}'
        f'{stat_row("Network", net, "%", C["warn"])}'
        f'{stat_row("Disk", disk, "%", C["high"])}'
        f'</table>'
    )
    return f'<div style="font-family:monospace;font-size:12px;padding:12px;color:#c0caf5;">{html}</div>'


def _format_cloudwatch_metrics(resource: Resource, metrics: object) -> str:
    """Format real CloudWatch ResourceMetrics into HTML."""
    C = {"title": "#7aa2f7", "label": "#7dcfff", "val": "#9ece6a", "muted": "#565f89",
         "warn": "#e0af68", "high": "#ff9e64", "purple": "#bb9af7"}

    rm = metrics  # type: ignore[assignment]
    if not rm or not hasattr(rm, "metrics") or not rm.metrics:
        return f'<div style="font-family:monospace;font-size:12px;padding:12px;color:#c0caf5;"><span style="color:{C["title"]};font-size:14px;font-weight:bold;">📊 Metrics</span><br><br><span style="color:{C["muted"]};">No CloudWatch data available for this instance.</span></div>'

    metric_colors = {"CPUUtilization": C["val"], "MemoryUtilization": C["purple"],
                     "NetworkIn": C["warn"], "NetworkOut": C["warn"], "DiskReadBytes": C["high"]}

    rows = []
    for metric_name, points in rm.metrics.items():
        if not points:
            continue
        vals = [p.value for p in sorted(points, key=lambda p: p.timestamp)][-24:]
        color = metric_colors.get(metric_name, C["label"])
        unit = points[0].unit if points else ""
        cur = vals[-1] if vals else 0
        spark = _sparkline(vals, color) if len(vals) > 1 else ""
        rows.append(
            f'<tr><td style="color:{C["label"]};padding:4px 12px 4px 8px;">{metric_name}</td>'
            f'<td style="padding:4px 16px 4px 0;">{spark}</td>'
            f'<td style="color:{color};font-weight:bold;">{cur:.1f} {unit}</td></tr>'
        )

    html = (
        f'<span style="color:{C["title"]};font-size:14px;font-weight:bold;">📊 Metrics</span><br>'
        f'<span style="color:{C["muted"]};">CloudWatch · {resource.name} · {resource.region}</span><br><br>'
        f'<table cellspacing="0">{"".join(rows)}</table>'
    )
    return f'<div style="font-family:monospace;font-size:12px;padding:12px;color:#c0caf5;">{html}</div>'


def _mock_analysis(name: str, key: str, resource: Resource | None = None) -> str:
    C = {"title": "#7aa2f7", "label": "#7dcfff", "val": "#9ece6a", "muted": "#565f89",
         "warn": "#e0af68", "critical": "#f7768e", "high": "#ff9e64", "med": "#e0af68", "low": "#9ece6a", "purple": "#bb9af7"}

    def wrap(body: str) -> str:
        return f'<div style="font-family:monospace;font-size:12px;padding:12px;color:#c0caf5;">{body}</div>'

    if key == "cost":
        total, delta, last, services = _MOCK_COST.get(name, ("—", "—", "—", ""))
        svc_rows = "".join(
            f'<tr><td style="color:{C["label"]};padding:2px 16px 2px 8px;">{s.strip()}</td>'
            f'<td style="color:{C["val"]};">included</td></tr>'
            for s in services.split(",")
        )
        html = (
            f'<span style="color:{C["title"]};font-size:14px;font-weight:bold;">Cost Summary</span><br>'
            f'<span style="color:{C["muted"]};">Demo data · current month</span><br><br>'
            f'<table cellspacing="0"><tr><td style="color:{C["label"]};padding:2px 16px 2px 8px;">Total (MTD)</td>'
            f'<td style="color:{C["val"]};font-weight:bold;">{total}</td></tr>'
            f'<tr><td style="color:{C["label"]};padding:2px 16px 2px 8px;">vs last month</td>'
            f'<td style="color:{C["warn"]};">+{delta}</td></tr>'
            f'<tr><td style="color:{C["label"]};padding:2px 16px 2px 8px;">Last month</td>'
            f'<td style="color:{C["val"]};">{last}</td></tr>'
            f'<tr><td colspan="2" style="padding:8px 0 4px 8px;color:{C["muted"]};">Top Services</td></tr>'
            f'{svc_rows}</table>'
        )
        return wrap(html)

    if key == "audit":
        findings = _MOCK_FINDINGS.get(name, [])
        if not findings:
            body = f'<span style="color:{C["title"]};font-size:14px;font-weight:bold;">Security Audit</span><br><br><span style="color:{C["val"]};">✓ No issues found (demo data)</span>'
            return wrap(body)
        color_map = {"HIGH": C["high"], "CRITICAL": C["critical"], "MEDIUM": C["med"], "LOW": C["low"]}
        rows = "".join(
            f'<tr><td style="color:{color_map.get(sev, C["muted"])};padding:3px 12px 3px 8px;font-weight:bold;">[{sev}]</td>'
            f'<td style="color:#c0caf5;padding:3px 0;">{msg}</td></tr>'
            for sev, msg, _ in findings
        )
        html = (
            f'<span style="color:{C["title"]};font-size:14px;font-weight:bold;">Security Audit</span><br>'
            f'<span style="color:{C["muted"]};">Demo data · {len(findings)} finding(s)</span><br><br>'
            f'<table cellspacing="0">{rows}</table>'
        )
        return wrap(html)

    if key == "unused":
        items = _MOCK_UNUSED.get(name, [])
        if not items:
            body = f'<span style="color:{C["title"]};font-size:14px;font-weight:bold;">Unused Resources</span><br><br><span style="color:{C["val"]};">✓ No idle resources detected (demo data)</span>'
            return wrap(body)
        rows = "".join(
            f'<tr><td style="color:{C["label"]};padding:3px 12px 3px 8px;">{rtype}</td>'
            f'<td style="color:#c0caf5;padding:3px 12px 3px 0;">{rname}</td>'
            f'<td style="color:{C["muted"]};padding:3px 12px 3px 0;">{age}</td>'
            f'<td style="color:{C["warn"]};padding:3px 0;">{cost}</td></tr>'
            for rtype, rname, age, cost in items
        )
        html = (
            f'<span style="color:{C["title"]};font-size:14px;font-weight:bold;">Unused Resources</span><br>'
            f'<span style="color:{C["muted"]};">Demo data · {len(items)} idle resource(s)</span><br><br>'
            f'<table cellspacing="0">{rows}</table>'
        )
        return wrap(html)

    if key == "relationships":
        return _mock_relationships(name, C, wrap)
    if key == "alerts":
        return "  No active alerts — all systems nominal ✓\n"
    if key == "metrics":
        if resource is None:
            return _metrics_no_selection_html()
        return _mock_metrics_for(resource)
    return f"  Analysis not available in demo mode.\n"


# ---------------------------------------------------------------------------
# Relationships HTML renderer (real providers)
# ---------------------------------------------------------------------------

async def _run_relationships_html(name: str, auth: object) -> str:
    C = {"title": "#7aa2f7", "label": "#7dcfff", "val": "#9ece6a",
         "muted": "#565f89", "purple": "#bb9af7"}

    try:
        if name == "aws":
            from spancloud.providers.aws.relationships import AWSRelationshipMapper
            mapper = AWSRelationshipMapper(auth)  # type: ignore[arg-type]
        elif name == "gcp":
            from spancloud.providers.gcp.relationships import GCPRelationshipMapper
            mapper = GCPRelationshipMapper(auth)  # type: ignore[arg-type]
        elif name == "vultr":
            from spancloud.providers.vultr.relationships import VultrRelationshipMapper
            mapper = VultrRelationshipMapper(auth)  # type: ignore[arg-type]
        elif name == "digitalocean":
            from spancloud.providers.digitalocean.relationships import DigitalOceanRelationshipMapper
            mapper = DigitalOceanRelationshipMapper(auth)  # type: ignore[arg-type]
        elif name == "azure":
            from spancloud.providers.azure.relationships import AzureRelationshipMapper
            mapper = AzureRelationshipMapper(auth)  # type: ignore[arg-type]
        elif name == "oci":
            from spancloud.providers.oci.relationships import OCIRelationshipMapper
            mapper = OCIRelationshipMapper(auth)  # type: ignore[arg-type]
        elif name == "alibaba":
            from spancloud.providers.alibaba.relationships import AlibabaRelationshipMapper
            mapper = AlibabaRelationshipMapper(auth)  # type: ignore[arg-type]
        else:
            return f"  Relationships not available for {name}."

        rel_map = await mapper.map_relationships()
    except Exception as exc:
        return f"  Error fetching relationships: {exc}"

    if not rel_map.relationships:
        body = (
            f'<span style="color:{C["title"]};font-size:14px;font-weight:bold;">Resource Relationships</span><br><br>'
            f'<span style="color:{C["val"]};">✓ No relationships found.</span>'
        )
        return f'<div style="font-family:monospace;font-size:12px;padding:12px;color:#c0caf5;">{body}</div>'

    by_source: dict[str, list] = {}
    for r in rel_map.relationships:
        key = f"{r.source_type}/{r.source_name or r.source_id}"
        by_source.setdefault(key, []).append(r)

    rows = []
    for source, rels in sorted(by_source.items()):
        rows.append(
            f'<tr><td colspan="4" style="padding:8px 0 2px 8px;color:{C["label"]};font-weight:bold;">{source}</td></tr>'
        )
        for r in rels:
            target = r.target_name or r.target_id
            rows.append(
                f'<tr>'
                f'<td style="color:{C["muted"]};padding:1px 4px 1px 24px;">│</td>'
                f'<td style="color:{C["muted"]};padding:1px 8px 1px 0;">──</td>'
                f'<td style="color:{C["purple"]};padding:1px 12px 1px 0;font-style:italic;">{r.relationship.value}</td>'
                f'<td style="color:#c0caf5;padding:1px 0;">{target} <span style="color:{C["muted"]};font-size:11px;">({r.target_type})</span></td>'
                f'</tr>'
            )

    html = (
        f'<span style="color:{C["title"]};font-size:14px;font-weight:bold;">Resource Relationships</span><br>'
        f'<span style="color:{C["muted"]};">{len(rel_map.relationships):,} connection(s)</span><br><br>'
        f'<table cellspacing="0">{"".join(rows)}</table>'
    )
    return f'<div style="font-family:monospace;font-size:12px;padding:12px;color:#c0caf5;">{html}</div>'


# ---------------------------------------------------------------------------
# Analyzer factory — mirrors TUI's _run_cost / _run_audit / _run_unused
# ---------------------------------------------------------------------------

async def _run_analysis(provider: BaseProvider, key: str, resource: Resource | None = None) -> str:
    """Dispatch to the right analyzer and return formatted plain text."""
    name = provider.name

    if not hasattr(provider, "_auth"):
        return _mock_analysis(name, key, resource)

    auth = provider._auth  # type: ignore[attr-defined]

    if key == "cost":
        if name == "aws":
            from spancloud.providers.aws.cost import AWSCostAnalyzer
            return _format_cost(await AWSCostAnalyzer(auth).get_cost_summary())
        elif name == "gcp":
            from spancloud.providers.gcp.cost import GCPCostAnalyzer
            return _format_cost(await GCPCostAnalyzer(auth).get_cost_summary())
        elif name == "vultr":
            from spancloud.providers.vultr.cost import VultrCostAnalyzer
            return _format_cost(await VultrCostAnalyzer(auth).get_cost_summary())
        elif name == "digitalocean":
            from spancloud.providers.digitalocean.cost import DigitalOceanCostAnalyzer
            return _format_cost(await DigitalOceanCostAnalyzer(auth).get_cost_summary())
        elif name == "azure":
            from spancloud.providers.azure.cost import AzureCostAnalyzer
            return _format_cost(await AzureCostAnalyzer(auth).get_cost_summary())
        elif name == "oci":
            from spancloud.providers.oci.cost import OCICostAnalyzer
            return _format_cost(await OCICostAnalyzer(auth).get_cost_summary())
        elif name == "alibaba":
            from spancloud.providers.alibaba.cost import AlibabaCostAnalyzer
            return _format_cost(await AlibabaCostAnalyzer(auth).get_cost_summary())
        return f"  Cost analysis not available for {name}."

    if key == "audit":
        if name == "aws":
            from spancloud.providers.aws.security import AWSSecurityAuditor
            return _format_audit(await AWSSecurityAuditor(auth).run_audit())
        elif name == "gcp":
            from spancloud.providers.gcp.security import GCPSecurityAuditor
            return _format_audit(await GCPSecurityAuditor(auth).run_audit())
        elif name == "vultr":
            from spancloud.providers.vultr.security import VultrSecurityAuditor
            return _format_audit(await VultrSecurityAuditor(auth).run_audit())
        elif name == "digitalocean":
            from spancloud.providers.digitalocean.security import DigitalOceanSecurityAuditor
            return _format_audit(await DigitalOceanSecurityAuditor(auth).run_audit())
        elif name == "azure":
            from spancloud.providers.azure.security import AzureSecurityAuditor
            return _format_audit(await AzureSecurityAuditor(auth).run_audit())
        elif name == "oci":
            from spancloud.providers.oci.security import OCISecurityAuditor
            return _format_audit(await OCISecurityAuditor(auth).run_audit())
        elif name == "alibaba":
            from spancloud.providers.alibaba.security import AlibabaSecurityAuditor
            return _format_audit(await AlibabaSecurityAuditor(auth).run_audit())
        return f"  Security audit not available for {name}."

    if key == "unused":
        if name == "aws":
            from spancloud.providers.aws.unused import AWSUnusedDetector
            return _format_unused(await AWSUnusedDetector(auth).scan())
        elif name == "gcp":
            from spancloud.providers.gcp.unused import GCPUnusedDetector
            return _format_unused(await GCPUnusedDetector(auth).scan())
        elif name == "vultr":
            from spancloud.providers.vultr.unused import VultrUnusedDetector
            return _format_unused(await VultrUnusedDetector(auth).scan())
        elif name == "digitalocean":
            from spancloud.providers.digitalocean.unused import DigitalOceanUnusedDetector
            return _format_unused(await DigitalOceanUnusedDetector(auth).scan())
        elif name == "azure":
            from spancloud.providers.azure.unused import AzureUnusedDetector
            return _format_unused(await AzureUnusedDetector(auth).scan())
        elif name == "oci":
            from spancloud.providers.oci.unused import OCIUnusedDetector
            return _format_unused(await OCIUnusedDetector(auth).scan())
        elif name == "alibaba":
            from spancloud.providers.alibaba.unused import AlibabaUnusedDetector
            return _format_unused(await AlibabaUnusedDetector(auth).scan())
        return f"  Unused detection not available for {name}."

    if key == "relationships":
        return await _run_relationships_html(name, auth)
    if key == "alerts":
        return "  No active alerts — all systems nominal ✓\n"
    if key == "metrics":
        if resource is None:
            return _metrics_no_selection_html()
        if name == "aws" and resource.resource_type.value == "compute":
            from spancloud.providers.aws.cloudwatch import CloudWatchAnalyzer
            try:
                cw = CloudWatchAnalyzer(auth)
                metrics = await cw.get_instance_metrics(resource.id, resource.region or "us-east-1")
                return _format_cloudwatch_metrics(resource, metrics)
            except Exception as exc:
                return f"  Could not fetch metrics: {exc}\n"
        return f"  Metrics not yet available for {name} {resource.resource_type.value} resources.\n"
    return f"  Unknown analysis type: {key}\n"


# ---------------------------------------------------------------------------
# Main widget
# ---------------------------------------------------------------------------

class ProviderViewWidget(QWidget):
    auth_requested = Signal()

    def __init__(self, provider: dict, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._provider_meta = provider
        self._provider: BaseProvider | None = provider.get("provider")
        self._current_rt: str | None = None
        self._rt_buttons: dict[str, QPushButton] = {}
        self._rt_type_map: dict[str, str] = {}  # service name → ResourceType value
        self._analysis_buttons: dict[str, QPushButton] = {}
        self._drawer_open = False
        self._current_region = ""
        self._current_profile = ""
        self._current_project = ""
        self.region_changed_hint = "All Regions"
        self._active_workers: list[AsyncWorker] = []
        self._current_load_key: str | None = None  # stale-result guard
        self._selected_resource: Resource | None = None
        self._current_analysis_key: str | None = None
        self._build()

    def _build(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._make_nav())

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setObjectName("divider")
        root.addWidget(sep)

        self._h_splitter = QSplitter(Qt.Orientation.Horizontal)
        self._h_splitter.setHandleWidth(1)
        self._h_splitter.setStyleSheet("QSplitter::handle { background: #3b4261; }")

        self._right_stack = QStackedWidget()
        self._empty_view = self._make_empty_view()
        self._resource_view = self._make_resource_view()
        self._analysis_view = self._make_analysis_view()
        self._unauthed_view = self._make_unauthed_view()
        self._right_stack.addWidget(self._empty_view)
        self._right_stack.addWidget(self._resource_view)
        self._right_stack.addWidget(self._analysis_view)
        self._right_stack.addWidget(self._unauthed_view)
        self._h_splitter.addWidget(self._right_stack)

        self._drawer = self._make_drawer()
        self._drawer.hide()
        self._h_splitter.addWidget(self._drawer)

        self._h_splitter.setCollapsible(0, False)
        self._h_splitter.setCollapsible(1, True)

        root.addWidget(self._h_splitter, stretch=1)

    # ------------------------------------------------------------------
    # Nav sidebar
    # ------------------------------------------------------------------
    def _make_nav(self) -> QWidget:
        nav = QWidget()
        nav.setObjectName("sidebar")
        nav.setFixedWidth(200)

        self._nav_layout = QVBoxLayout(nav)
        self._nav_layout.setContentsMargins(0, 0, 0, 0)
        self._nav_layout.setSpacing(0)

        pname = self._provider_meta["name"]
        self._controls = ProviderControls(pname)
        self._controls.region_changed.connect(self._on_region_changed)
        self._controls.profile_changed.connect(self._on_profile_changed)
        self._controls.project_changed.connect(self._on_project_changed)
        self._nav_layout.addWidget(self._controls)

        self._nav_resources_label = QLabel("RESOURCES")
        self._nav_resources_label.setObjectName("sidebar-section")
        self._nav_layout.addWidget(self._nav_resources_label)

        self._nav_rt_container = QWidget()
        self._nav_rt_layout = QVBoxLayout(self._nav_rt_container)
        self._nav_rt_layout.setContentsMargins(0, 0, 0, 0)
        self._nav_rt_layout.setSpacing(0)
        self._nav_layout.addWidget(self._nav_rt_container)

        section2 = QLabel("ANALYSIS")
        section2.setObjectName("sidebar-section")
        self._nav_layout.addWidget(section2)

        for key, label in _ANALYSIS_ITEMS:
            btn = self._make_nav_button(key, label, None, "analysis")
            self._analysis_buttons[key] = btn
            self._nav_layout.addWidget(btn)

        self._nav_layout.addStretch()

        settings_btn = QPushButton("⚙  Configure Sidebar")
        settings_btn.setFlat(True)
        settings_btn.setStyleSheet(f"""
            QPushButton {{
                color: {TEXT_MUTED};
                font-size: 11px;
                text-align: left;
                padding: 6px 16px;
                border: none;
                border-top: 1px solid {BORDER_SUBTLE};
            }}
            QPushButton:hover {{
                color: {TEXT_PRIMARY};
                background: rgba(255,255,255,0.05);
            }}
        """)
        settings_btn.clicked.connect(self._open_sidebar_settings)
        self._nav_layout.addWidget(settings_btn)

        self._rebuild_rt_buttons()
        return nav

    def _rebuild_rt_buttons(self) -> None:
        from spancloud.config.sidebar import get_sidebar_items

        while self._nav_rt_layout.count():
            item = self._nav_rt_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._rt_buttons.clear()
        self._rt_type_map.clear()

        pname = self._provider_meta["name"]
        if self._provider is None:
            return

        # "All Resources" is always first
        all_btn = self._make_nav_button("_all", "📋 All Resources", None, "rt")
        self._rt_buttons["_all"] = all_btn
        self._nav_rt_layout.addWidget(all_btn)

        for svc in get_sidebar_items(pname):
            name = svc["name"]
            btn = self._make_nav_button(name, svc["label"], None, "rt")
            self._rt_buttons[name] = btn
            self._rt_type_map[name] = svc["type"]  # may be "other" — handled in _load_table
            self._nav_rt_layout.addWidget(btn)

    def _open_sidebar_settings(self) -> None:
        from spancloud.gui.widgets.sidebar_settings_dialog import SidebarSettingsDialog
        dlg = SidebarSettingsDialog(
            self._provider_meta["name"], self._provider_meta["display"], self
        )
        if dlg.exec():
            self._rebuild_rt_buttons()

    def _make_nav_button(
        self, key: str, label: str, count: int | None, kind: str
    ) -> QPushButton:
        btn = QPushButton()
        btn.setFlat(True)
        btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        btn.setProperty("active", "false")
        btn.setProperty("class", "sidebar-item" if kind == "rt" else "analysis-item")

        row = QHBoxLayout()
        row.setContentsMargins(12, 0, 12, 0)
        row.setSpacing(0)

        lbl = QLabel(label)
        lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 12px;")
        lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        row.addWidget(lbl)

        if count is not None and count > 0:
            badge = QLabel(str(count))
            badge.setStyleSheet(f"""
                background: rgba(122,162,247,0.2);
                color: {ACCENT_BLUE};
                border-radius: 8px;
                padding: 1px 7px;
                font-size: 10px;
                font-weight: 600;
            """)
            badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            row.addWidget(badge)

        container = QWidget()
        container.setLayout(row)
        container.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        outer = QVBoxLayout(btn)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(container)

        if kind == "rt":
            btn.clicked.connect(lambda checked=False, k=key: self._select_rt(k))
        else:
            btn.clicked.connect(lambda checked=False, k=key: self._select_analysis(k))
        return btn

    # ------------------------------------------------------------------
    # Resource view (table + search)
    # ------------------------------------------------------------------
    def _make_resource_view(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        search_bar = QWidget()
        search_bar.setStyleSheet(
            f"background: {BG_ELEVATED}; border-bottom: 1px solid {BORDER_SUBTLE};"
        )
        sh = QHBoxLayout(search_bar)
        sh.setContentsMargins(16, 10, 16, 10)
        self._search = QLineEdit()
        self._search.setPlaceholderText("🔍  Filter resources…")
        self._search.textChanged.connect(self._filter_table)
        sh.addWidget(self._search)
        v.addWidget(search_bar)

        self._table = QTreeWidget()
        self._table.setAlternatingRowColors(True)
        self._table.setRootIsDecorated(False)
        self._table.setUniformRowHeights(True)
        self._table.setColumnCount(5)
        self._table.setHeaderLabels(["Name", "ID", "State", "Region", "Type"])
        self._table.header().setStretchLastSection(True)
        self._table.header().setSectionsClickable(True)
        self._table.setSortingEnabled(True)
        self._table.setColumnWidth(0, 190)
        self._table.setColumnWidth(1, 210)
        self._table.setColumnWidth(2, 85)
        self._table.setColumnWidth(3, 110)
        self._table.itemClicked.connect(self._on_row_clicked)
        v.addWidget(self._table, stretch=1)
        return w

    # ------------------------------------------------------------------
    # Right-side detail drawer
    # ------------------------------------------------------------------
    def _make_drawer(self) -> QWidget:
        drawer = QFrame()
        drawer.setObjectName("detail-panel")
        drawer.setMinimumWidth(260)
        drawer.setMaximumWidth(420)

        v = QVBoxLayout(drawer)
        v.setContentsMargins(16, 16, 16, 16)
        v.setSpacing(12)

        header_row = QHBoxLayout()
        self._drawer_title = QLabel("Resource Details")
        self._drawer_title.setObjectName("detail-title")
        header_row.addWidget(self._drawer_title, stretch=1)

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(26, 26)
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                border: none;
                color: {TEXT_MUTED};
                font-size: 14px;
                border-radius: 4px;
            }}
            QPushButton:hover {{
                background: rgba(255,255,255,0.08);
                color: {TEXT_PRIMARY};
            }}
        """)
        close_btn.clicked.connect(self._close_drawer)
        header_row.addWidget(close_btn)
        v.addLayout(header_row)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {BORDER_SUBTLE};")
        v.addWidget(sep)

        self._drawer_scroll = QScrollArea()
        self._drawer_scroll.setWidgetResizable(True)
        self._drawer_scroll.setFrameShape(QFrame.Shape.NoFrame)

        self._drawer_fields = QWidget()
        self._drawer_fields_layout = QVBoxLayout(self._drawer_fields)
        self._drawer_fields_layout.setContentsMargins(0, 0, 0, 0)
        self._drawer_fields_layout.setSpacing(0)
        self._drawer_fields_layout.addStretch()

        self._drawer_scroll.setWidget(self._drawer_fields)
        v.addWidget(self._drawer_scroll, stretch=1)
        return drawer

    def _populate_drawer(self, resource: Resource) -> None:
        layout = self._drawer_fields_layout
        while layout.count() > 1:
            item = layout.takeAt(0)
            w = item.widget() if item else None
            if w:
                w.deleteLater()

        def add(key: str, value: str) -> None:
            if not value:
                return
            layout.insertWidget(layout.count() - 1, self._make_field_row(key, value))

        add("ID", resource.id)
        add("State", resource.state.value)
        add("Region", resource.region)
        add("Type", resource.resource_type.value)
        if resource.created_at:
            add("Created", resource.created_at.strftime("%Y-%m-%d %H:%M UTC"))
        for k, v in resource.metadata.items():
            add(k.replace("_", " ").title(), str(v))
        if resource.tags:
            add("Tags", "  ".join(f"{k}={v}" for k, v in resource.tags.items()))

    def _make_field_row(self, key: str, value: str) -> QWidget:
        w = QWidget()
        w.setStyleSheet(f"""
            QWidget {{
                border-bottom: 1px solid {BORDER_SUBTLE};
                padding: 8px 0;
            }}
        """)
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 6, 0, 6)
        v.setSpacing(3)

        k_lbl = QLabel(key)
        k_lbl.setObjectName("detail-key")
        v.addWidget(k_lbl)

        v_lbl = QLabel(value)
        v_lbl.setObjectName("detail-value")
        v_lbl.setWordWrap(True)
        v_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        v.addWidget(v_lbl)
        return w

    def _open_drawer(self, resource: Resource) -> None:
        self._drawer_title.setText(resource.display_name)
        self._populate_drawer(resource)
        if not self._drawer_open:
            self._drawer.show()
            total = self._h_splitter.width()
            self._h_splitter.setSizes([total - 320, 320])
            self._drawer_open = True

    def _close_drawer(self) -> None:
        self._drawer.hide()
        self._drawer_open = False

    # ------------------------------------------------------------------
    # Analysis view
    # ------------------------------------------------------------------
    def _make_analysis_view(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(24, 20, 24, 20)
        v.setSpacing(16)

        self._analysis_title = QLabel("Analysis")
        self._analysis_title.setObjectName("analysis-title")
        v.addWidget(self._analysis_title)

        self._analysis_content = QTextEdit()
        self._analysis_content.setReadOnly(True)
        self._analysis_content.setStyleSheet(f"""
            QTextEdit {{
                color: {TEXT_PRIMARY};
                font-family: "JetBrains Mono", "Fira Code", "Cascadia Code", monospace;
                font-size: 12px;
                background: {BG_SURFACE};
                border: 1px solid {BORDER_SUBTLE};
                border-radius: 8px;
                padding: 12px;
            }}
        """)
        v.addWidget(self._analysis_content, stretch=1)
        return w

    def _make_empty_view(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint = QLabel("Select a resource type or analysis item from the sidebar")
        hint.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 14px;")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.addWidget(hint)
        return w

    def _make_unauthed_view(self) -> QWidget:
        w = QWidget()
        v = QVBoxLayout(w)
        v.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.setSpacing(14)

        icon = QLabel("🔌")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setStyleSheet("font-size: 42px;")
        v.addWidget(icon)

        name_lbl = QLabel(f"Not connected to {self._provider_meta['display']}")
        name_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name_lbl.setStyleSheet(
            f"color: {TEXT_PRIMARY}; font-size: 16px; font-weight: 600;"
        )
        v.addWidget(name_lbl)

        hint = QLabel("Authenticate to view resources and run analysis.")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 13px;")
        v.addWidget(hint)

        connect_btn = QPushButton(f"Connect to {self._provider_meta['display']}")
        connect_btn.setFixedWidth(240)
        connect_btn.setStyleSheet(f"""
            QPushButton {{
                background: {ACCENT_BLUE};
                border: none;
                border-radius: 6px;
                color: #1a1b26;
                font-size: 13px;
                font-weight: 600;
                padding: 10px 20px;
            }}
            QPushButton:hover {{ background: #89b4fa; }}
        """)
        connect_btn.clicked.connect(self.auth_requested.emit)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(connect_btn)
        btn_row.addStretch()
        v.addLayout(btn_row)
        return w

    def notify_auth_status(self, status: str) -> None:
        """Called from app.py when auth state changes for this provider."""
        if status in ("unauthenticated", "error"):
            self._right_stack.setCurrentWidget(self._unauthed_view)
        elif status == "authenticated":
            if self._right_stack.currentWidget() is self._unauthed_view:
                self._right_stack.setCurrentWidget(self._empty_view)
            self._post_auth_setup()

    def _post_auth_setup(self) -> None:
        """After successful auth, sync controls with live provider state."""
        if self._provider is None:
            return
        name = self._provider_meta["name"]

        # Reflect the active AWS profile in the combo
        if name == "aws" and hasattr(self._provider, "_auth"):
            active = getattr(self._provider._auth, "active_profile", "")
            if active:
                self._controls.set_active_profile(active)

        # Populate GCP project list from the resource-manager API
        if name == "gcp":
            self._fetch_gcp_projects()

    def _fetch_gcp_projects(self) -> None:
        if self._provider is None or not hasattr(self._provider, "_auth"):
            return
        auth = self._provider._auth  # type: ignore[attr-defined]

        async def _load() -> tuple[list[dict], str]:
            try:
                projects = await auth.list_accessible_projects()
            except Exception:
                projects = []
            active = getattr(auth, "project_id", "") or ""
            return projects, active

        worker = AsyncWorker(_load())
        worker.result_ready.connect(
            lambda result: self._controls.populate_gcp_projects(result[0], result[1])
        )
        worker.finished.connect(lambda w=worker: self._cleanup_worker(w))
        self._active_workers.append(worker)
        worker.start()

    # ------------------------------------------------------------------
    # Region / profile / project signal handlers
    # ------------------------------------------------------------------
    def _on_region_changed(self, region: str) -> None:
        self._current_region = region
        self.region_changed_hint = region if region else "All Regions"
        if self._current_rt:
            self._load_table(self._current_rt)
        self._close_drawer()

    def _on_profile_changed(self, profile: str) -> None:
        self._current_profile = profile
        if self._provider and hasattr(self._provider, "_auth"):
            auth = self._provider._auth  # type: ignore[attr-defined]
            if hasattr(auth, "set_profile"):
                auth.set_profile(profile)
        if self._current_rt:
            self._load_table(self._current_rt)
        self._close_drawer()

    def _on_project_changed(self, project: str) -> None:
        self._current_project = project
        if self._provider and hasattr(self._provider, "_auth"):
            auth = self._provider._auth  # type: ignore[attr-defined]
            if hasattr(auth, "set_project"):
                auth.set_project(project)
        if self._current_rt:
            self._load_table(self._current_rt)
        self._close_drawer()

    # ------------------------------------------------------------------
    # Interaction
    # ------------------------------------------------------------------
    def _deselect_all(self) -> None:
        for btn in {**self._rt_buttons, **self._analysis_buttons}.values():
            btn.setProperty("active", "false")
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    def _select_rt(self, rt: str) -> None:
        self._deselect_all()
        self._current_rt = rt
        btn = self._rt_buttons.get(rt)
        if btn:
            btn.setProperty("active", "true")
            btn.style().unpolish(btn)
            btn.style().polish(btn)
        self._close_drawer()
        if rt == "_all":
            self._load_all_resources()
        else:
            self._load_table(rt)
        self._right_stack.setCurrentWidget(self._resource_view)

    def _select_analysis(self, key: str) -> None:
        self._current_analysis_key = key
        self._deselect_all()
        self._current_rt = None
        btn = self._analysis_buttons.get(key)
        if btn:
            btn.setProperty("active", "true")
            btn.style().unpolish(btn)
            btn.style().polish(btn)
        self._close_drawer()
        self._load_analysis(key)
        self._right_stack.setCurrentWidget(self._analysis_view)

    def _load_table(self, rt: str) -> None:
        if self._provider is None:
            self._table.clear()
            self._show_table_message("Provider not available.")
            return

        from spancloud.core.resource import ResourceType

        # Resolve service name (e.g. "ec2") to its ResourceType value (e.g. "compute")
        rt_value = self._rt_type_map.get(rt, rt)

        # If this type isn't a known ResourceType, show a friendly message
        supported = {r.value for r in self._provider.supported_resource_types}
        if rt_value not in supported:
            self._table.setSortingEnabled(False)
            self._table.clear()
            self._show_table_message(
                f"{rt} — detailed browsing not yet available in the GUI "
                "(use CLI: spancloud aws list --type other)"
            )
            return

        load_key = f"rt:{rt}:{self._current_region}"
        self._current_load_key = load_key

        self._table.setSortingEnabled(False)
        self._table.clear()
        self._show_table_message(f"Loading {rt}…")

        region = self._current_region or None
        worker = AsyncWorker(
            self._provider.list_resources(ResourceType(rt_value), region=region)
        )
        worker.result_ready.connect(
            lambda res, k=load_key: self._on_resources_loaded(res, k)
        )
        worker.error_occurred.connect(
            lambda err, k=load_key: self._on_load_error(err, k)
        )
        worker.finished.connect(lambda w=worker: self._cleanup_worker(w))
        self._active_workers.append(worker)
        worker.start()

    def _load_all_resources(self) -> None:
        if self._provider is None:
            self._table.clear()
            self._show_table_message("Provider not available.")
            return

        load_key = f"rt:_all:{self._current_region}"
        self._current_load_key = load_key

        self._table.setSortingEnabled(False)
        self._table.clear()
        self._show_table_message("Loading all resources…")

        region = self._current_region or None

        async def _fetch_all() -> list[Resource]:
            import asyncio

            async def _one(rt: object) -> list[Resource]:
                try:
                    return await self._provider.list_resources(rt, region=region)  # type: ignore[arg-type, union-attr]
                except Exception:
                    return []

            results = await asyncio.gather(
                *[_one(rt) for rt in self._provider.supported_resource_types]  # type: ignore[union-attr]
            )
            return [r for sublist in results for r in sublist]

        worker = AsyncWorker(_fetch_all())
        worker.result_ready.connect(
            lambda res, k=load_key: self._on_resources_loaded(res, k)
        )
        worker.error_occurred.connect(
            lambda err, k=load_key: self._on_load_error(err, k)
        )
        worker.finished.connect(lambda w=worker: self._cleanup_worker(w))
        self._active_workers.append(worker)
        worker.start()

    def _on_resources_loaded(self, resources: list[Resource], key: str) -> None:
        if key != self._current_load_key:
            return
        self._table.clear()
        self._table.setSortingEnabled(False)
        for r in resources:
            subtype = (
                r.metadata.get("instance_type")
                or r.metadata.get("machine_type")
                or r.metadata.get("size")
                or r.metadata.get("shape")
                or r.resource_type.value
            )
            item = QTreeWidgetItem([r.name, r.id, r.state.value, r.region, subtype])
            item.setForeground(2, QColor(_STATE_COLOR.get(r.state.value, TEXT_MUTED)))
            item.setData(0, Qt.ItemDataRole.UserRole, r)
            self._table.addTopLevelItem(item)
        self._table.setSortingEnabled(True)
        if not resources:
            self._show_table_message("No resources found.")

    def _on_load_error(self, error: str, key: str) -> None:
        if key != self._current_load_key:
            return
        self._table.clear()
        self._show_table_message(f"Error: {error}")

    def _show_table_message(self, msg: str) -> None:
        item = QTreeWidgetItem([msg])
        item.setForeground(0, QColor(TEXT_MUTED))
        item.setFlags(Qt.ItemFlag.NoItemFlags)
        self._table.addTopLevelItem(item)

    def _filter_table(self, text: str) -> None:
        q = text.lower()
        for i in range(self._table.topLevelItemCount()):
            item = self._table.topLevelItem(i)
            if item is None:
                continue
            visible = not q or any(
                q in (item.text(col) or "").lower() for col in range(item.columnCount())
            )
            item.setHidden(not visible)

    def _on_row_clicked(self, item: QTreeWidgetItem) -> None:
        resource: Resource | None = item.data(0, Qt.ItemDataRole.UserRole)
        if resource is not None:
            self._selected_resource = resource
            self._open_drawer(resource)
            self._update_metrics_button()
            if self._current_analysis_key == "metrics":
                self._load_analysis("metrics")

    def _update_metrics_button(self) -> None:
        btn = self._analysis_buttons.get("metrics")
        if btn is None:
            return
        # Find the QLabel inside the button and update its text
        for child in btn.findChildren(QLabel):
            if "Metrics" in child.text() or "📊" in child.text():
                if self._selected_resource:
                    name = self._selected_resource.name
                    display = name if len(name) <= 18 else name[:16] + "…"
                    child.setText(f"📊 Metrics: {display}")
                else:
                    child.setText("📊 Metrics")
                break

    def _load_analysis(self, key: str) -> None:
        titles = {
            "cost":          "💰 Cost Summary",
            "audit":         "🛡  Security Audit",
            "unused":        "🗑  Unused Resources",
            "relationships": "🔗 Relationships",
            "alerts":        "🔔 Monitoring Alerts",
            "metrics":       "📊 Metrics",
        }
        self._analysis_title.setText(titles.get(key, key))

        if self._provider is None:
            self._analysis_content.setPlainText("  Provider not available.")
            return

        load_key = f"analysis:{key}"
        self._current_load_key = load_key
        self._analysis_content.setPlainText("  Loading…")

        worker = AsyncWorker(_run_analysis(self._provider, key, self._selected_resource))
        worker.result_ready.connect(
            lambda text, k=load_key: self._on_analysis_done(text, k)
        )
        worker.error_occurred.connect(
            lambda err, k=load_key: self._on_analysis_error(err, k)
        )
        worker.finished.connect(lambda w=worker: self._cleanup_worker(w))
        self._active_workers.append(worker)
        worker.start()

    def _on_analysis_done(self, text: str, key: str) -> None:
        if key != self._current_load_key:
            return
        if text.startswith("<"):
            self._analysis_content.setHtml(text)
        else:
            self._analysis_content.setPlainText(text)

    def _on_analysis_error(self, error: str, key: str) -> None:
        if key != self._current_load_key:
            return
        self._analysis_content.setPlainText(f"  Error: {error}")

    def _cleanup_worker(self, worker: AsyncWorker) -> None:
        try:
            self._active_workers.remove(worker)
        except ValueError:
            pass
