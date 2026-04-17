"""Tests for security audit logic."""

from __future__ import annotations

from unittest.mock import MagicMock


class TestAWSSecurityAuditor:
    """Tests for AWS security audit checks."""

    def _make_auditor(self):
        from skyforge.providers.aws.security import AWSSecurityAuditor

        auth = MagicMock()
        return AWSSecurityAuditor(auth)

    def test_sensitive_ports_defined(self) -> None:
        from skyforge.providers.aws.security import _SENSITIVE_PORTS

        assert 22 in _SENSITIVE_PORTS
        assert 3389 in _SENSITIVE_PORTS
        assert 3306 in _SENSITIVE_PORTS
        assert _SENSITIVE_PORTS[22] == "SSH"


class TestGCPSecurityAuditor:
    """Tests for GCP security audit port parsing and checks."""

    def _make_auditor(self):
        from skyforge.providers.gcp.security import GCPSecurityAuditor

        auth = MagicMock()
        return GCPSecurityAuditor(auth)

    def test_parse_port_range_single(self) -> None:
        auditor = self._make_auditor()
        assert auditor._parse_port_range("80") == (80, 80)

    def test_parse_port_range_range(self) -> None:
        auditor = self._make_auditor()
        assert auditor._parse_port_range("8080-8090") == (8080, 8090)

    def test_parse_port_range_ssh(self) -> None:
        auditor = self._make_auditor()
        start, end = auditor._parse_port_range("22")
        assert start <= 22 <= end

    def test_sensitive_ports_defined(self) -> None:
        from skyforge.providers.gcp.security import _SENSITIVE_PORTS

        assert 22 in _SENSITIVE_PORTS
        assert 5432 in _SENSITIVE_PORTS


class TestAWSCostAnalyzer:
    """Tests for AWS cost analyzer initialization."""

    def test_can_create(self) -> None:
        from skyforge.providers.aws.cost import AWSCostAnalyzer

        auth = MagicMock()
        analyzer = AWSCostAnalyzer(auth)
        assert analyzer is not None


class TestGCPCostAnalyzer:
    """Tests for GCP cost analyzer initialization."""

    def test_can_create(self) -> None:
        from skyforge.providers.gcp.cost import GCPCostAnalyzer

        auth = MagicMock()
        analyzer = GCPCostAnalyzer(auth)
        assert analyzer is not None


class TestAWSUnusedDetector:
    """Tests for AWS unused detector initialization."""

    def test_can_create(self) -> None:
        from skyforge.providers.aws.unused import AWSUnusedDetector

        auth = MagicMock()
        detector = AWSUnusedDetector(auth)
        assert detector is not None


class TestGCPUnusedDetector:
    """Tests for GCP unused detector initialization."""

    def test_can_create(self) -> None:
        from skyforge.providers.gcp.unused import GCPUnusedDetector

        auth = MagicMock()
        detector = GCPUnusedDetector(auth)
        assert detector is not None


class TestAWSRelationshipMapper:
    """Tests for AWS relationship mapper initialization."""

    def test_can_create(self) -> None:
        from skyforge.providers.aws.relationships import AWSRelationshipMapper

        auth = MagicMock()
        mapper = AWSRelationshipMapper(auth)
        assert mapper is not None


class TestGCPRelationshipMapper:
    """Tests for GCP relationship mapper initialization."""

    def test_can_create(self) -> None:
        from skyforge.providers.gcp.relationships import GCPRelationshipMapper

        auth = MagicMock()
        mapper = GCPRelationshipMapper(auth)
        assert mapper is not None
