"""Per-provider view: resource-type sidebar + table + right drawer + analysis."""

from __future__ import annotations

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

from spancloud.gui.theme import (
    ACCENT_BLUE,
    ACCENT_YELLOW,
    BG_ELEVATED,
    BG_SURFACE,
    BORDER_SUBTLE,
    STATUS_ERROR,
    STATUS_MUTED,
    STATUS_OK,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)
from spancloud.gui.widgets.provider_controls import ProviderControls

# ---------------------------------------------------------------------------
# Mock data
# ---------------------------------------------------------------------------
_MOCK_RESOURCES: dict[str, dict[str, list[dict]]] = {
    "aws": {
        "compute": [
            {"id": "i-0a1b2c3d4e5f", "name": "web-prod-01",    "state": "running",  "region": "us-east-1", "type": "t3.medium",   "public_ip": "54.210.167.99",  "private_ip": "10.0.1.42",  "launched": "2025-11-15T08:23:11Z", "vpc": "vpc-0a1b2c3d", "az": "us-east-1a"},
            {"id": "i-1b2c3d4e5f6g", "name": "web-prod-02",    "state": "running",  "region": "us-east-1", "type": "t3.medium",   "public_ip": "54.210.167.100", "private_ip": "10.0.1.43",  "launched": "2025-11-15T08:25:00Z", "vpc": "vpc-0a1b2c3d", "az": "us-east-1b"},
            {"id": "i-2c3d4e5f6g7h", "name": "api-prod-01",    "state": "running",  "region": "us-west-2", "type": "c6i.large",   "public_ip": "35.160.100.50",  "private_ip": "10.1.0.10",  "launched": "2025-12-01T14:00:00Z", "vpc": "vpc-1b2c3d4e", "az": "us-west-2a"},
            {"id": "i-3d4e5f6g7h8i", "name": "batch-worker-1", "state": "stopped",  "region": "us-east-1", "type": "m5.xlarge",   "public_ip": "",               "private_ip": "10.0.2.55",  "launched": "2025-10-01T09:00:00Z", "vpc": "vpc-0a1b2c3d", "az": "us-east-1c"},
            {"id": "i-4e5f6g7h8i9j", "name": "db-replica",     "state": "running",  "region": "eu-west-1", "type": "r6i.large",   "public_ip": "",               "private_ip": "172.16.0.5", "launched": "2026-01-10T00:00:00Z", "vpc": "vpc-2c3d4e5f", "az": "eu-west-1a"},
            {"id": "i-5f6g7h8i9j0k", "name": "dev-sandbox",    "state": "stopped",  "region": "us-east-1", "type": "t3.small",    "public_ip": "",               "private_ip": "10.0.3.7",   "launched": "2025-09-20T11:00:00Z", "vpc": "vpc-0a1b2c3d", "az": "us-east-1a"},
        ],
        "storage": [
            {"id": "arn:aws:s3:::prod-assets",  "name": "prod-assets",  "state": "running", "region": "us-east-1", "type": "S3 Bucket",     "size": "14.2 GB",  "objects": "41,230", "versioning": "Enabled",  "encryption": "AES-256"},
            {"id": "arn:aws:s3:::data-archive", "name": "data-archive", "state": "running", "region": "us-east-1", "type": "S3 Bucket",     "size": "220.5 GB", "objects": "8,412",  "versioning": "Suspended","encryption": "AES-256"},
            {"id": "arn:aws:s3:::logs-bucket",  "name": "logs-bucket",  "state": "running", "region": "us-east-1", "type": "S3 Bucket",     "size": "3.1 GB",   "objects": "120,000","versioning": "Disabled", "encryption": "None"},
            {"id": "vol-0a1b2c3d",              "name": "db-data-vol",  "state": "running", "region": "us-east-1", "type": "EBS gp3 500GB", "size": "500 GB",   "objects": "",       "versioning": "",         "encryption": "KMS"},
        ],
        "database": [
            {"id": "prod-mysql",    "name": "prod-mysql",    "state": "running", "region": "us-east-1", "type": "RDS MySQL 8.0",       "engine": "MySQL 8.0",      "size": "db.r6g.large",   "multi_az": "Yes", "storage": "200 GB"},
            {"id": "analytics-pg",  "name": "analytics-pg",  "state": "running", "region": "us-east-1", "type": "RDS PostgreSQL 15",   "engine": "PostgreSQL 15",  "size": "db.m6g.xlarge",  "multi_az": "No",  "storage": "500 GB"},
            {"id": "cache-prod",    "name": "cache-prod",    "state": "running", "region": "us-east-1", "type": "ElastiCache Redis",   "engine": "Redis 7.0",      "size": "cache.r6g.large","multi_az": "Yes", "storage": ""},
        ],
        "network": [
            {"id": "vpc-0a1b2c3d", "name": "prod-vpc",    "state": "running", "region": "us-east-1", "type": "VPC",            "cidr": "10.0.0.0/16",  "subnets": "6", "igw": "Yes"},
            {"id": "vpc-1b2c3d4e", "name": "staging-vpc", "state": "running", "region": "us-west-2", "type": "VPC",            "cidr": "10.1.0.0/16",  "subnets": "4", "igw": "Yes"},
            {"id": "sg-0a1b2c3d",  "name": "web-sg",      "state": "running", "region": "us-east-1", "type": "Security Group", "cidr": "",             "subnets": "", "igw": ""},
        ],
        "serverless": [
            {"id": "api-handler",   "name": "api-handler",   "state": "running", "region": "us-east-1", "type": "Lambda Python 3.12", "memory": "512 MB",  "timeout": "30s",  "invocations": "2.4M/mo"},
            {"id": "image-resizer", "name": "image-resizer", "state": "running", "region": "us-east-1", "type": "Lambda Node.js 20",  "memory": "1024 MB", "timeout": "60s",  "invocations": "180K/mo"},
            {"id": "scheduled-job", "name": "scheduled-job", "state": "stopped", "region": "us-east-1", "type": "Lambda Python 3.12", "memory": "256 MB",  "timeout": "300s", "invocations": "0/mo"},
        ],
        "container": [
            {"id": "prod-eks",  "name": "prod-eks",  "state": "running", "region": "us-east-1", "type": "EKS 1.29",     "nodes": "6", "version": "1.29", "endpoint": "https://abc.eks.amazonaws.com"},
            {"id": "ecs-tasks", "name": "ecs-tasks", "state": "running", "region": "us-east-1", "type": "ECS Fargate",  "nodes": "",  "version": "",     "endpoint": ""},
        ],
    },
    "gcp": {
        "compute": [
            {"id": "web-1", "name": "web-1", "state": "running", "region": "us-central1", "type": "n2-standard-2", "public_ip": "34.132.10.1",  "private_ip": "10.128.0.2", "launched": "2026-01-01T00:00:00Z", "vpc": "default", "az": "us-central1-a"},
            {"id": "web-2", "name": "web-2", "state": "running", "region": "us-central1", "type": "n2-standard-2", "public_ip": "34.132.10.2",  "private_ip": "10.128.0.3", "launched": "2026-01-01T00:00:00Z", "vpc": "default", "az": "us-central1-b"},
            {"id": "api-1", "name": "api-1", "state": "running", "region": "us-east1",    "type": "c2-standard-4", "public_ip": "35.231.20.5",  "private_ip": "10.142.0.2", "launched": "2026-02-15T00:00:00Z", "vpc": "default", "az": "us-east1-b"},
        ],
        "storage": [
            {"id": "gs://prod-data",   "name": "prod-data",   "state": "running", "region": "US",          "type": "GCS Standard", "size": "88.3 GB",  "objects": "12,400", "versioning": "Enabled",  "encryption": "Google-managed"},
            {"id": "gs://ml-datasets", "name": "ml-datasets", "state": "running", "region": "US-CENTRAL1", "type": "GCS Nearline", "size": "420.1 GB", "objects": "3,200",  "versioning": "Disabled", "encryption": "Google-managed"},
        ],
        "database": [
            {"id": "prod-pg",  "name": "prod-pg",  "state": "running", "region": "us-central1", "type": "Cloud SQL PostgreSQL 15", "engine": "PostgreSQL 15", "size": "db-n1-standard-4", "multi_az": "Yes", "storage": "200 GB"},
            {"id": "analytics","name": "analytics","state": "running", "region": "US",           "type": "BigQuery Dataset",        "engine": "BigQuery",      "size": "",                  "multi_az": "",    "storage": "1.2 TB"},
        ],
        "container": [
            {"id": "prod-gke", "name": "prod-gke", "state": "running", "region": "us-central1", "type": "GKE 1.29", "nodes": "4", "version": "1.29", "endpoint": "https://34.72.100.1"},
        ],
    },
    "digitalocean": {
        "compute": [
            {"id": "12345678", "name": "web-1", "state": "running", "region": "nyc3", "type": "s-2vcpu-4gb", "public_ip": "104.236.1.1",  "private_ip": "10.0.0.2", "launched": "2026-01-10T00:00:00Z", "vpc": "prod-vpc", "az": "nyc3"},
            {"id": "12345679", "name": "web-2", "state": "running", "region": "nyc3", "type": "s-2vcpu-4gb", "public_ip": "104.236.1.2",  "private_ip": "10.0.0.3", "launched": "2026-01-10T00:00:00Z", "vpc": "prod-vpc", "az": "nyc3"},
            {"id": "12345680", "name": "db-01", "state": "running", "region": "sfo3", "type": "s-4vcpu-8gb", "public_ip": "165.227.10.1", "private_ip": "10.1.0.2", "launched": "2025-12-01T00:00:00Z", "vpc": "prod-vpc", "az": "sfo3"},
        ],
        "database": [
            {"id": "db-abc123", "name": "prod-pg", "state": "running", "region": "nyc3", "type": "PostgreSQL 15", "engine": "PostgreSQL 15", "size": "db-s-2vcpu-4gb", "multi_az": "No", "storage": "25 GB"},
        ],
        "storage": [
            {"id": "vol-abc", "name": "data-vol", "state": "running", "region": "nyc3", "type": "Block 100GB", "size": "100 GB", "objects": "", "versioning": "", "encryption": ""},
        ],
        "network": [
            {"id": "vpc-1", "name": "prod-vpc", "state": "running", "region": "nyc3", "type": "VPC", "cidr": "10.0.0.0/16", "subnets": "", "igw": ""},
        ],
        "container": [
            {"id": "k8s-1", "name": "prod-doks", "state": "running", "region": "nyc3", "type": "DOKS 1.29", "nodes": "3", "version": "1.29", "endpoint": "https://k8s.do.com/k8s-1"},
        ],
    },
    "oci": {
        "compute": [
            {"id": "ocid1.instance.oc1..aaa", "name": "web-prod-1", "state": "running", "region": "us-ashburn-1", "type": "VM.Standard.E4.Flex", "public_ip": "130.35.10.1", "private_ip": "10.0.1.10", "launched": "2026-01-05T00:00:00Z", "vpc": "prod-vcn", "az": "AD-1"},
            {"id": "ocid1.instance.oc1..bbb", "name": "app-server", "state": "running", "region": "us-ashburn-1", "type": "VM.Standard.E4.Flex", "public_ip": "130.35.10.2", "private_ip": "10.0.1.11", "launched": "2026-02-01T00:00:00Z", "vpc": "prod-vcn", "az": "AD-2"},
        ],
        "storage": [
            {"id": "ocid1.bucket..xyz", "name": "data-bucket", "state": "running", "region": "us-ashburn-1", "type": "Object Storage", "size": "22.4 GB",  "objects": "5,100", "versioning": "Disabled", "encryption": "Oracle-managed"},
            {"id": "ocid1.volume..abc", "name": "data-vol",    "state": "running", "region": "us-ashburn-1", "type": "Block Volume",    "size": "200 GB",   "objects": "",      "versioning": "",          "encryption": "Oracle-managed"},
        ],
        "database": [
            {"id": "ocid1.autonomousdb..a1", "name": "prod-adb", "state": "running", "region": "us-ashburn-1", "type": "Autonomous DB", "engine": "ATP OLTP", "size": "1 OCPU", "multi_az": "Yes", "storage": "1 TB"},
        ],
        "network": [
            {"id": "ocid1.vcn..v1", "name": "prod-vcn", "state": "running", "region": "us-ashburn-1", "type": "VCN", "cidr": "10.0.0.0/16", "subnets": "4", "igw": "Yes"},
        ],
        "container": [
            {"id": "ocid1.cluster..c1", "name": "prod-oke", "state": "running", "region": "us-ashburn-1", "type": "OKE 1.29", "nodes": "3", "version": "1.29", "endpoint": "https://cluster.io"},
        ],
        "load_balancer": [
            {"id": "ocid1.lb..l1", "name": "main-lb", "state": "running", "region": "us-ashburn-1", "type": "Flexible LB", "public_ip": "130.35.20.1", "private_ip": "", "launched": "", "vpc": "prod-vcn", "az": ""},
        ],
        "dns": [
            {"id": "ocid1.dns-zone..z1", "name": "example.com", "state": "running", "region": "global", "type": "DNS Zone", "public_ip": "", "private_ip": "", "launched": "", "vpc": "", "az": ""},
        ],
    },
}

_RESOURCE_TYPES = [
    ("compute",       "🖥  Compute"),
    ("storage",       "📦 Storage"),
    ("network",       "🌐 Network"),
    ("database",      "💾 Database"),
    ("serverless",    "⚡ Serverless"),
    ("container",     "📦 Container"),
    ("load_balancer", "⚖  Load Balancer"),
    ("dns",           "🌐 DNS"),
]

_ANALYSIS_ITEMS = [
    ("cost",          "💰 Cost Summary"),
    ("audit",         "🛡  Security Audit"),
    ("unused",        "🗑  Unused Resources"),
    ("relationships", "🔗 Relationships"),
    ("alerts",        "🔔 Monitoring Alerts"),
    ("metrics",       "📊 Metrics"),
]

_STATE_COLOR = {
    "running":    STATUS_OK,
    "stopped":    STATUS_ERROR,
    "pending":    ACCENT_YELLOW,
    "terminated": TEXT_MUTED,
    "error":      STATUS_ERROR,
    "unknown":    TEXT_MUTED,
}

_MOCK_COST = """  Monthly cost estimate
  ─────────────────────────────────────────────────────
  EC2 Instances                        $1,240.00 / mo
    ├ web-prod-01 (t3.medium)              $30.37
    ├ web-prod-02 (t3.medium)              $30.37
    ├ api-prod-01 (c6i.large)              $61.20
    ├ db-replica  (r6i.large)              $91.98
    └ 2 others                             $26.08

  RDS / ElastiCache                      $480.00 / mo
  S3 Storage                              $18.40 / mo
  Data Transfer                           $62.00 / mo
  Lambda Invocations                       $3.20 / mo
  ─────────────────────────────────────────────────────
  Estimated total                      $1,803.60 / mo
"""

_MOCK_AUDIT = """  Security Audit — 6 findings
  ─────────────────────────────────────────────────────
  🔴 CRITICAL  S3 bucket prod-assets has public read ACL
  🔴 CRITICAL  Security group sg-0a1b2c3d allows 0.0.0.0/0:22
  🟡 MEDIUM    RDS prod-mysql multi-AZ not enabled
  🟡 MEDIUM    2 EC2 instances missing IMDSv2 enforcement
  🔵 LOW       3 S3 buckets missing access logging
  🔵 LOW       Lambda api-handler has overly broad IAM role
"""

_MOCK_UNUSED = """  Unused / Idle Resources
  ─────────────────────────────────────────────────────
  dev-sandbox (EC2 t3.small)
    Stopped for 47 days — est. $8.00/mo if running

  data-archive (S3 Bucket)
    0 GET requests in 90 days — storage cost $4.20/mo

  vol-0a1b2c3d (EBS gp3 500GB)
    Unattached for 12 days — $40.00/mo

  scheduled-job (Lambda)
    0 invocations in 30 days
"""

# Fields to show in the right-side detail drawer per resource type
_DETAIL_FIELDS: dict[str, list[str]] = {
    "compute":      ["state", "region", "type", "public_ip", "private_ip", "vpc", "az", "launched"],
    "storage":      ["state", "region", "type", "size", "objects", "versioning", "encryption"],
    "database":     ["state", "region", "type", "engine", "size", "multi_az", "storage"],
    "network":      ["state", "region", "type", "cidr", "subnets", "igw"],
    "serverless":   ["state", "region", "type", "memory", "timeout", "invocations"],
    "container":    ["state", "region", "type", "nodes", "version", "endpoint"],
    "load_balancer":["state", "region", "type", "public_ip", "private_ip", "vpc"],
    "dns":          ["state", "region", "type"],
}


class ProviderViewWidget(QWidget):
    def __init__(self, provider: dict, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._provider = provider
        self._current_rt: str | None = None
        self._rt_buttons: dict[str, QPushButton] = {}
        self._analysis_buttons: dict[str, QPushButton] = {}
        self._drawer_open = False
        self._current_region = ""
        self._current_profile = ""
        self._current_project = ""
        self.region_changed_hint = "All Regions"
        self._build()

    def _build(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Inner nav sidebar (resource types + analysis) ───────────────
        root.addWidget(self._make_nav())

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setObjectName("divider")
        root.addWidget(sep)

        # ── Main content + right drawer in a splitter ───────────────────
        self._h_splitter = QSplitter(Qt.Orientation.Horizontal)
        self._h_splitter.setHandleWidth(1)
        self._h_splitter.setStyleSheet("QSplitter::handle { background: #3b4261; }")

        # Centre: stacked (resource table | analysis | empty)
        self._right_stack = QStackedWidget()
        self._empty_view = self._make_empty_view()
        self._resource_view = self._make_resource_view()
        self._analysis_view = self._make_analysis_view()
        self._right_stack.addWidget(self._empty_view)
        self._right_stack.addWidget(self._resource_view)
        self._right_stack.addWidget(self._analysis_view)
        self._h_splitter.addWidget(self._right_stack)

        # Right: detail drawer (hidden until a row is clicked)
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

        v = QVBoxLayout(nav)
        v.setContentsMargins(0, 0, 0, 8)
        v.setSpacing(0)

        # ── Region / profile / project controls ─────────────────────────
        self._controls = ProviderControls(self._provider["name"])
        self._controls.region_changed.connect(self._on_region_changed)
        self._controls.profile_changed.connect(self._on_profile_changed)
        self._controls.project_changed.connect(self._on_project_changed)
        v.addWidget(self._controls)

        section = QLabel("RESOURCES")
        section.setObjectName("sidebar-section")
        v.addWidget(section)

        provider_resources = _MOCK_RESOURCES.get(self._provider["name"], {})
        for rt, label in _RESOURCE_TYPES:
            if rt in provider_resources:
                count = len(provider_resources[rt])
                btn = self._make_nav_button(rt, label, count, "rt")
                self._rt_buttons[rt] = btn
                v.addWidget(btn)

        section2 = QLabel("ANALYSIS")
        section2.setObjectName("sidebar-section")
        v.addWidget(section2)

        for key, label in _ANALYSIS_ITEMS:
            btn = self._make_nav_button(key, label, None, "analysis")
            self._analysis_buttons[key] = btn
            v.addWidget(btn)

        v.addStretch()
        return nav

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
        sh.addWidget(self._search)
        v.addWidget(search_bar)

        self._table = QTreeWidget()
        self._table.setAlternatingRowColors(True)
        self._table.setRootIsDecorated(False)
        self._table.setUniformRowHeights(True)
        self._table.setColumnCount(5)
        self._table.setHeaderLabels(["Name", "ID", "State", "Region", "Type"])
        self._table.header().setStretchLastSection(True)
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

        # Header row: title + close button
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

        # Scrollable key-value fields
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

    def _populate_drawer(self, r: dict, rt: str) -> None:
        layout = self._drawer_fields_layout

        # Clear existing fields (keep trailing stretch)
        while layout.count() > 1:
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        fields = _DETAIL_FIELDS.get(rt, list(r.keys()))
        for field in fields:
            val = r.get(field, "")
            if val == "" or val is None:
                continue
            row = self._make_field_row(field.replace("_", " ").title(), str(val))
            layout.insertWidget(layout.count() - 1, row)

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

    def _open_drawer(self, r: dict, rt: str) -> None:
        self._drawer_title.setText(r["name"])
        self._populate_drawer(r, rt)
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
        display = region if region else "All Regions"
        # Reload current resource type with new region filter (mockup: just refreshes)
        if self._current_rt:
            self._load_table(self._current_rt)
        self._close_drawer()
        # Bubble up to toolbar via parent chain — toolbar will be updated by MainWindow
        self.region_changed_hint = display

    def _on_profile_changed(self, profile: str) -> None:
        self._current_profile = profile
        if self._current_rt:
            self._load_table(self._current_rt)
        self._close_drawer()

    def _on_project_changed(self, project: str) -> None:
        self._current_project = project
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
        self._load_table(rt)
        self._close_drawer()
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
        self._table.clear()
        resources = _MOCK_RESOURCES.get(self._provider["name"], {}).get(rt, [])
        for r in resources:
            item = QTreeWidgetItem([
                r["name"],
                r["id"],
                r["state"],
                r["region"],
                r["type"],
            ])
            item.setForeground(2, QColor(_STATE_COLOR.get(r["state"], TEXT_MUTED)))
            item.setData(0, Qt.ItemDataRole.UserRole, r)
            self._table.addTopLevelItem(item)

    def _on_row_clicked(self, item: QTreeWidgetItem) -> None:
        data = item.data(0, Qt.ItemDataRole.UserRole)
        if data and self._current_rt:
            self._open_drawer(data, self._current_rt)

    def _load_analysis(self, key: str) -> None:
        titles = {
            "cost":          "💰 Cost Summary",
            "audit":         "🛡  Security Audit",
            "unused":        "🗑  Unused Resources",
            "relationships": "🔗 Relationships",
            "alerts":        "🔔 Monitoring Alerts",
            "metrics":       "📊 Metrics",
        }
        content = {
            "cost":          _MOCK_COST,
            "audit":         _MOCK_AUDIT,
            "unused":        _MOCK_UNUSED,
            "relationships": "\n  Relationships graph coming soon…\n",
            "alerts":        "\n  No active alerts — all systems nominal ✓\n",
            "metrics":       "\n  Select a resource first, then view metrics here.\n",
        }
        self._analysis_title.setText(titles.get(key, key))
        self._analysis_content.setText(content.get(key, ""))
