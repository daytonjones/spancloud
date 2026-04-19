"""Per-provider view: resource-type sidebar + table + right drawer + analysis."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
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
# Analysis text formatters (plain monospace, no Rich markup)
# ---------------------------------------------------------------------------

def _format_cost(summary: object) -> str:  # CostSummary
    from decimal import Decimal
    M = "  "
    LW, AW = 42, 14
    SEP = M + "─" * (LW + AW)

    def row(label: str, amount: str, indent: str = "") -> str:
        return f"{M}{indent}{label:<{LW - len(indent)}}{amount:>{AW}}"

    lines = [
        row(f"Monthly cost  ({summary.period_start} → {summary.period_end})", ""),
        SEP,
    ]
    if summary.notes:
        lines.append(f"{M}Note: {summary.notes}")
        lines.append("")

    for svc in summary.by_service[:15]:
        pct = (
            f"{float(svc.cost / summary.total_cost * 100):.1f}%"
            if summary.total_cost > 0 else "—"
        )
        lines.append(row(f"{svc.service}  ({pct})", f"${svc.cost:>10,.2f} / mo"))

    lines.append(SEP)
    lines.append(row("Estimated total", f"${summary.total_cost:>10,.2f} / mo"))

    if summary.daily_costs:
        recent = summary.daily_costs[-7:]
        max_cost = max(d.cost for d in recent) if recent else Decimal(1)
        lines += ["", row("Daily trend (last 7 days)", ""), SEP]
        for day in recent:
            bar_len = int(float(day.cost / max_cost) * 20) if max_cost > 0 else 0
            lines.append(row(str(day.date), f"${day.cost:>10,.2f}") + "  " + "█" * bar_len)

    lines.append("")
    return "\n".join(lines)


def _format_audit(result: object) -> str:  # SecurityAuditResult
    M = "  "
    SEP = M + "─" * 58
    SEV_DOT = {
        "critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🔵", "info": "⚪",
    }

    def row(dot: str, sev: str, text: str) -> str:
        return f"{M}{dot}  {sev:<10}  {text}"

    lines = [
        f"{M}Security Audit — {len(result.findings)} finding(s)  ({result.summary})",
        SEP,
    ]
    if not result.findings:
        lines.append(f"{M}No security issues found ✓")
    else:
        for f in sorted(result.findings, key=lambda x: x.severity.value):
            dot = SEV_DOT.get(f.severity.value, "⚪")
            lines.append(row(dot, f.severity.value.upper(), f"{f.resource_type}/{f.resource_id}"))
            lines.append(f"{M}               {f.title}")
            lines.append(f"{M}               → {f.recommendation}")
            lines.append("")
    lines.append("")
    return "\n".join(lines)


def _format_unused(report: object) -> str:  # UnusedResourceReport
    M = "  "
    NW, TW, RW, SW = 20, 18, 24, 14
    SEP = M + "─" * (NW + TW + RW + SW)

    def hdr() -> str:
        return f"{M}{'Resource':<{NW}}{'Type':<{TW}}{'Reason':<{RW}}{'Savings':>{SW}}"

    def row(name: str, rtype: str, reason: str, cost: str) -> str:
        return f"{M}{name:<{NW}}{rtype:<{TW}}{reason:<{RW}}{cost:>{SW}}"

    total = report.total_estimated_monthly_savings
    lines = [
        f"{M}Unused / Idle Resources — {report.total_count} item(s)",
        f"{M}Potential savings: ${total:,.2f}/mo" if total > 0 else f"{M}No cost estimates available.",
        SEP,
        hdr(),
        SEP,
    ]
    for r in report.resources:
        lines.append(row(
            r.resource_name[:NW - 1],
            r.resource_type[:TW - 1],
            r.reason[:RW - 1],
            r.estimated_monthly_savings or "—",
        ))
    lines += [SEP, ""]
    return "\n".join(lines)


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
    def __init__(self, provider: dict, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._provider_meta = provider
        self._provider: BaseProvider | None = provider.get("provider")
        self._current_rt: str | None = None
        self._rt_buttons: dict[str, QPushButton] = {}
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
        self._right_stack.addWidget(self._empty_view)
        self._right_stack.addWidget(self._resource_view)
        self._right_stack.addWidget(self._analysis_view)
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
        from spancloud.core.resource import ResourceType

        while self._nav_rt_layout.count():
            item = self._nav_rt_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._rt_buttons.clear()

        pname = self._provider_meta["name"]
        if self._provider is None:
            return

        supported = {rt.value for rt in self._provider.supported_resource_types}
        seen: set[str] = set()

        for svc in get_sidebar_items(pname):
            rt = svc["type"]
            if rt in seen or rt not in supported:
                continue
            seen.add(rt)
            btn = self._make_nav_button(rt, svc["label"], None, "rt")
            self._rt_buttons[rt] = btn
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

        self._analysis_content = QLabel()
        self._analysis_content.setWordWrap(True)
        self._analysis_content.setAlignment(
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft
        )
        self._analysis_content.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self._analysis_content.setStyleSheet(f"""
            color: {TEXT_PRIMARY};
            font-family: "JetBrains Mono", "Fira Code", "Cascadia Code", monospace;
            font-size: 12px;
            background: {BG_SURFACE};
            border: 1px solid {BORDER_SUBTLE};
            border-radius: 8px;
            padding: 16px;
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
        load_key = f"rt:{rt}:{self._current_region}"
        self._current_load_key = load_key

        self._table.setSortingEnabled(False)
        self._table.clear()
        self._show_table_message(f"Loading {rt}…")

        region = self._current_region or None
        worker = AsyncWorker(
            self._provider.list_resources(ResourceType(rt), region=region)
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
            self._analysis_content.setText("  Provider not available.")
            return

        load_key = f"analysis:{key}"
        self._current_load_key = load_key
        self._analysis_content.setText("  Loading…")

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
        self._analysis_content.setText(text)

    def _on_analysis_error(self, error: str, key: str) -> None:
        if key != self._current_load_key:
            return
        self._analysis_content.setText(f"  Error: {error}")

    def _cleanup_worker(self, worker: AsyncWorker) -> None:
        try:
            self._active_workers.remove(worker)
        except ValueError:
            pass
