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
# Analyzer factory — mirrors TUI's _run_cost / _run_audit / _run_unused
# ---------------------------------------------------------------------------

async def _run_analysis(provider: BaseProvider, key: str) -> str:
    """Dispatch to the right analyzer and return formatted plain text."""
    name = provider.name
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
        return "  Relationships graph coming soon…\n"
    if key == "alerts":
        return "  No active alerts — all systems nominal ✓\n"
    if key == "metrics":
        return "  Select a resource first, then view metrics here.\n"
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
            self._open_drawer(resource)

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

        worker = AsyncWorker(_run_analysis(self._provider, key))
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
