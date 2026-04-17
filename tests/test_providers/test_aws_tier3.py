"""Tests for AWS Tier 3 features: CloudWatch, Route53, S3 details, IAM, actions."""

from __future__ import annotations

from unittest.mock import MagicMock

from skyforge.core.resource import ResourceType


class TestCloudWatchAnalyzer:
    """Tests for CloudWatch alarm and metric models."""

    def test_can_create(self) -> None:
        from skyforge.providers.aws.cloudwatch import CloudWatchAnalyzer

        auth = MagicMock()
        analyzer = CloudWatchAnalyzer(auth)
        assert analyzer is not None

    def test_alarm_info_model(self) -> None:
        from skyforge.providers.aws.cloudwatch import AlarmInfo

        alarm = AlarmInfo(
            name="high-cpu",
            state="ALARM",
            metric_name="CPUUtilization",
            namespace="AWS/EC2",
            threshold="GreaterThanThreshold 80.0",
            dimensions={"InstanceId": "i-123"},
        )
        assert alarm.name == "high-cpu"
        assert alarm.state == "ALARM"
        assert alarm.dimensions["InstanceId"] == "i-123"

    def test_resource_metrics_model(self) -> None:
        from skyforge.providers.aws.cloudwatch import MetricPoint, ResourceMetrics

        metrics = ResourceMetrics(
            resource_id="i-123",
            resource_type="ec2_instance",
            metrics={
                "CPUUtilization": [
                    MetricPoint(timestamp="2026-04-16T10:00:00Z", value=45.2),
                    MetricPoint(timestamp="2026-04-16T10:05:00Z", value=52.1),
                ],
            },
        )
        assert metrics.resource_id == "i-123"
        assert len(metrics.metrics["CPUUtilization"]) == 2


class TestRoute53Resources:
    """Tests for Route53 resource discovery."""

    def test_can_create(self) -> None:
        from skyforge.providers.aws.route53 import Route53Resources

        auth = MagicMock()
        r53 = Route53Resources(auth)
        assert r53 is not None


class TestS3DetailAnalyzer:
    """Tests for S3 bucket detail models."""

    def test_can_create(self) -> None:
        from skyforge.providers.aws.s3_details import S3DetailAnalyzer

        auth = MagicMock()
        analyzer = S3DetailAnalyzer(auth)
        assert analyzer is not None

    def test_bucket_details_model(self) -> None:
        from skyforge.providers.aws.s3_details import BucketDetails, LifecycleRule

        details = BucketDetails(
            name="my-bucket",
            region="us-east-1",
            versioning="Enabled",
            encryption="aws:kms",
            policy_summary="2 statement(s): Allow, Deny",
            lifecycle_rules=[
                LifecycleRule(
                    id="archive-old",
                    status="Enabled",
                    transitions=["→ GLACIER after 90d"],
                    expiration_days=365,
                ),
            ],
            object_count="1,234",
            total_size="5.67 GB",
        )
        assert details.name == "my-bucket"
        assert details.versioning == "Enabled"
        assert len(details.lifecycle_rules) == 1
        assert details.lifecycle_rules[0].expiration_days == 365

    def test_lifecycle_rule_defaults(self) -> None:
        from skyforge.providers.aws.s3_details import LifecycleRule

        rule = LifecycleRule()
        assert rule.id == ""
        assert rule.expiration_days is None
        assert rule.transitions == []


class TestIAMResources:
    """Tests for IAM resource discovery."""

    def test_user_resources_can_create(self) -> None:
        from skyforge.providers.aws.iam import IAMUserResources

        auth = MagicMock()
        users = IAMUserResources(auth)
        assert users is not None

    def test_role_resources_can_create(self) -> None:
        from skyforge.providers.aws.iam import IAMRoleResources

        auth = MagicMock()
        roles = IAMRoleResources(auth)
        assert roles is not None

    def test_policy_resources_can_create(self) -> None:
        from skyforge.providers.aws.iam import IAMPolicyResources

        auth = MagicMock()
        policies = IAMPolicyResources(auth)
        assert policies is not None

    def test_extract_trusted_entities(self) -> None:
        from skyforge.providers.aws.iam import IAMRoleResources

        auth = MagicMock()
        roles = IAMRoleResources(auth)

        policy = {
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {
                        "Service": "ec2.amazonaws.com",
                        "AWS": "arn:aws:iam::123456:root",
                    },
                    "Action": "sts:AssumeRole",
                }
            ]
        }
        result = roles._extract_trusted_entities(policy)
        assert "ec2.amazonaws.com" in result
        assert "root" in result

    def test_extract_trusted_entities_empty(self) -> None:
        from skyforge.providers.aws.iam import IAMRoleResources

        auth = MagicMock()
        roles = IAMRoleResources(auth)
        assert roles._extract_trusted_entities({}) == ""


class TestEC2Actions:
    """Tests for EC2 resource actions."""

    def test_can_create(self) -> None:
        from skyforge.providers.aws.actions import EC2Actions

        auth = MagicMock()
        actions = EC2Actions(auth)
        assert actions is not None

    def test_action_verb_enum(self) -> None:
        from skyforge.providers.aws.actions import ActionVerb

        assert ActionVerb.START == "start"
        assert ActionVerb.STOP == "stop"
        assert ActionVerb.REBOOT == "reboot"
        assert ActionVerb.TERMINATE == "terminate"

    def test_action_result_model(self) -> None:
        from skyforge.providers.aws.actions import ActionResult

        result = ActionResult(
            success=True,
            action="stop",
            resource_id="i-123",
            resource_type="ec2_instance",
            provider="aws",
            previous_state="running",
            current_state="stopping",
            message="Successfully sent stop",
        )
        assert result.success is True
        assert result.previous_state == "running"

    def test_valid_state_transitions(self) -> None:
        from skyforge.providers.aws.actions import _VALID_STATES, ActionVerb

        assert "stopped" in _VALID_STATES[ActionVerb.START]
        assert "running" in _VALID_STATES[ActionVerb.STOP]
        assert "running" in _VALID_STATES[ActionVerb.REBOOT]
        assert "running" in _VALID_STATES[ActionVerb.TERMINATE]
        assert "stopped" in _VALID_STATES[ActionVerb.TERMINATE]


class TestAWSProviderTier3Integration:
    """Tests that new resource types are wired into AWSProvider."""

    def test_dns_in_supported_types(self) -> None:
        from skyforge.providers.aws.provider import AWSProvider

        provider = AWSProvider()
        assert ResourceType.DNS in provider.supported_resource_types

    def test_iam_in_supported_types(self) -> None:
        from skyforge.providers.aws.provider import AWSProvider

        provider = AWSProvider()
        assert ResourceType.IAM in provider.supported_resource_types
