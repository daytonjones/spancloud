"""Tests for GCP Tier 3 features: Cloud Monitoring, Cloud DNS, GCS details, actions."""

from __future__ import annotations

from unittest.mock import MagicMock

from skyforge.core.resource import ResourceType


class TestCloudMonitoringAnalyzer:
    """Tests for Cloud Monitoring models and analyzer."""

    def test_can_create(self) -> None:
        from skyforge.providers.gcp.monitoring import CloudMonitoringAnalyzer

        auth = MagicMock()
        analyzer = CloudMonitoringAnalyzer(auth)
        assert analyzer is not None

    def test_alert_info_model(self) -> None:
        from skyforge.providers.gcp.monitoring import AlertInfo

        alert = AlertInfo(
            name="policy-123",
            display_name="High CPU",
            enabled=True,
            conditions_count=2,
            notification_channels=1,
            combiner="OR",
        )
        assert alert.display_name == "High CPU"
        assert alert.conditions_count == 2

    def test_resource_metrics_model(self) -> None:
        from skyforge.providers.gcp.monitoring import MetricPoint, ResourceMetrics

        metrics = ResourceMetrics(
            resource_id="12345",
            metrics={
                "CPUUtilization": [
                    MetricPoint(timestamp="2026-04-16T10:00:00Z", value=0.45),
                    MetricPoint(timestamp="2026-04-16T10:05:00Z", value=0.52),
                ],
            },
        )
        assert len(metrics.metrics["CPUUtilization"]) == 2


class TestCloudDNSResources:
    """Tests for Cloud DNS resource discovery."""

    def test_can_create(self) -> None:
        from skyforge.providers.gcp.dns import CloudDNSResources

        auth = MagicMock()
        dns_res = CloudDNSResources(auth)
        assert dns_res is not None

    def test_map_records(self) -> None:
        from skyforge.providers.gcp.dns import CloudDNSResources

        auth = MagicMock()
        dns_res = CloudDNSResources(auth)

        mock_record = MagicMock()
        mock_record.name = "www.example.com."
        mock_record.record_type = "A"
        mock_record.ttl = 300
        mock_record.rrdatas = ["1.2.3.4"]

        resources = dns_res._map_records([mock_record], "my-zone")
        assert len(resources) == 1
        assert resources[0].name == "www.example.com"
        assert resources[0].metadata["record_type"] == "A"
        assert resources[0].metadata["values"] == "1.2.3.4"
        assert resources[0].metadata["resource_subtype"] == "dns_record"


class TestGCSDetailAnalyzer:
    """Tests for GCS bucket detail models."""

    def test_can_create(self) -> None:
        from skyforge.providers.gcp.gcs_details import GCSDetailAnalyzer

        auth = MagicMock()
        analyzer = GCSDetailAnalyzer(auth)
        assert analyzer is not None

    def test_bucket_details_model(self) -> None:
        from skyforge.providers.gcp.gcs_details import BucketDetails, LifecycleRule

        details = BucketDetails(
            name="my-bucket",
            location="US",
            location_type="multi-region",
            storage_class="STANDARD",
            versioning=True,
            encryption="CMEK (my-key)",
            lifecycle_rules=[
                LifecycleRule(
                    action="SetStorageClass",
                    storage_class="NEARLINE",
                    age_days=30,
                    condition="age >= 30d",
                ),
            ],
            object_count="5,000",
            total_size="1.23 GB",
        )
        assert details.versioning is True
        assert len(details.lifecycle_rules) == 1
        assert details.lifecycle_rules[0].age_days == 30

    def test_lifecycle_rule_defaults(self) -> None:
        from skyforge.providers.gcp.gcs_details import LifecycleRule

        rule = LifecycleRule()
        assert rule.action == ""
        assert rule.age_days is None


class TestGCEActions:
    """Tests for GCE resource actions."""

    def test_can_create(self) -> None:
        from skyforge.providers.gcp.actions import GCEActions

        auth = MagicMock()
        actions = GCEActions(auth)
        assert actions is not None

    def test_action_verb_enum(self) -> None:
        from skyforge.providers.gcp.actions import ActionVerb

        assert ActionVerb.START == "start"
        assert ActionVerb.STOP == "stop"
        assert ActionVerb.RESET == "reset"

    def test_action_result_model(self) -> None:
        from skyforge.providers.gcp.actions import ActionResult

        result = ActionResult(
            success=True,
            action="stop",
            resource_id="my-vm",
            previous_state="RUNNING",
            current_state="STOPPING",
            message="Sent stop",
        )
        assert result.success is True
        assert result.provider == "gcp"

    def test_valid_state_transitions(self) -> None:
        from skyforge.providers.gcp.actions import _VALID_STATES, ActionVerb

        assert "TERMINATED" in _VALID_STATES[ActionVerb.START]
        assert "SUSPENDED" in _VALID_STATES[ActionVerb.START]
        assert "RUNNING" in _VALID_STATES[ActionVerb.STOP]
        assert "RUNNING" in _VALID_STATES[ActionVerb.RESET]


class TestGCPProviderTier3Integration:
    """Tests that DNS is wired into GCPProvider."""

    def test_dns_in_supported_types(self) -> None:
        from skyforge.providers.gcp.provider import GCPProvider

        provider = GCPProvider()
        assert ResourceType.DNS in provider.supported_resource_types
