"""Tests for resource models."""

from __future__ import annotations

from skyforge.core.resource import Resource, ResourceState, ResourceType


class TestResource:
    """Tests for the Resource model."""

    def test_minimal_resource(self) -> None:
        r = Resource(
            id="i-123",
            name="test-instance",
            resource_type=ResourceType.COMPUTE,
            provider="aws",
        )
        assert r.id == "i-123"
        assert r.name == "test-instance"
        assert r.state == ResourceState.UNKNOWN
        assert r.tags == {}
        assert r.metadata == {}

    def test_display_name_prefers_name(self) -> None:
        r = Resource(
            id="i-123",
            name="my-server",
            resource_type=ResourceType.COMPUTE,
            provider="aws",
        )
        assert r.display_name == "my-server"

    def test_display_name_falls_back_to_id(self) -> None:
        r = Resource(
            id="i-123",
            name="",
            resource_type=ResourceType.COMPUTE,
            provider="aws",
        )
        assert r.display_name == "i-123"

    def test_str_representation(self) -> None:
        r = Resource(
            id="i-123",
            name="web-1",
            resource_type=ResourceType.COMPUTE,
            provider="aws",
            state=ResourceState.RUNNING,
        )
        assert str(r) == "aws:compute/web-1 (running)"

    def test_resource_with_tags_and_metadata(self) -> None:
        r = Resource(
            id="bucket-1",
            name="my-bucket",
            resource_type=ResourceType.STORAGE,
            provider="gcp",
            region="us-central1",
            state=ResourceState.RUNNING,
            tags={"env": "prod", "team": "platform"},
            metadata={"storage_class": "STANDARD"},
        )
        assert r.tags["env"] == "prod"
        assert r.metadata["storage_class"] == "STANDARD"
        assert r.region == "us-central1"


class TestResourceType:
    """Tests for ResourceType enum."""

    def test_string_values(self) -> None:
        assert ResourceType.COMPUTE == "compute"
        assert ResourceType.STORAGE == "storage"

    def test_all_types_are_strings(self) -> None:
        for rt in ResourceType:
            assert isinstance(rt.value, str)


class TestResourceState:
    """Tests for ResourceState enum."""

    def test_string_values(self) -> None:
        assert ResourceState.RUNNING == "running"
        assert ResourceState.STOPPED == "stopped"
