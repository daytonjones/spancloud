"""Tests for resource export (JSON, CSV, YAML)."""

from __future__ import annotations

import json

from skyforge.core.export import to_csv, to_json, to_yaml
from skyforge.core.resource import Resource, ResourceState, ResourceType


def _sample_resources() -> list[Resource]:
    return [
        Resource(
            id="i-123",
            name="web-server",
            resource_type=ResourceType.COMPUTE,
            provider="aws",
            region="us-east-1",
            state=ResourceState.RUNNING,
            tags={"env": "prod", "team": "platform"},
            metadata={"machine_type": "t3.micro", "resource_subtype": "ec2"},
        ),
        Resource(
            id="vpc-456",
            name="main-vpc",
            resource_type=ResourceType.NETWORK,
            provider="aws",
            region="us-east-1",
            state=ResourceState.RUNNING,
            tags={},
            metadata={"cidr_block": "10.0.0.0/16", "resource_subtype": "vpc"},
        ),
    ]


class TestJsonExport:
    def test_basic_json(self) -> None:
        result = to_json(_sample_resources())
        data = json.loads(result)
        assert len(data) == 2
        assert data[0]["id"] == "i-123"
        assert data[0]["name"] == "web-server"
        assert data[0]["tags"]["env"] == "prod"
        assert data[0]["metadata"]["machine_type"] == "t3.micro"

    def test_empty_list(self) -> None:
        result = to_json([])
        assert json.loads(result) == []

    def test_compact_json(self) -> None:
        result = to_json(_sample_resources(), pretty=False)
        assert "\n" not in result


class TestCsvExport:
    def test_basic_csv(self) -> None:
        result = to_csv(_sample_resources())
        lines = result.strip().split("\n")
        assert len(lines) == 3  # header + 2 rows
        header = lines[0]
        assert "id" in header
        assert "meta:machine_type" in header
        assert "tag:env" in header

    def test_empty_list(self) -> None:
        assert to_csv([]) == ""

    def test_values_in_rows(self) -> None:
        result = to_csv(_sample_resources())
        assert "web-server" in result
        assert "t3.micro" in result
        assert "prod" in result


class TestYamlExport:
    def test_basic_yaml(self) -> None:
        result = to_yaml(_sample_resources())
        assert "- id: i-123" in result
        assert "  name: web-server" in result
        assert "    env: prod" in result
        assert "    machine_type: t3.micro" in result

    def test_empty_list(self) -> None:
        assert to_yaml([]) == ""
