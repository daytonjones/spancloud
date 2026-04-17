"""Export resources to JSON, CSV, or YAML formats."""

from __future__ import annotations

import csv
import io
import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from skyforge.core.resource import Resource


def to_json(resources: list[Resource], pretty: bool = True) -> str:
    """Export resources to JSON.

    Args:
        resources: List of Resource objects.
        pretty: Whether to indent the output.

    Returns:
        JSON string.
    """
    data = [_resource_to_dict(r) for r in resources]
    return json.dumps(data, indent=2 if pretty else None, default=str)


def to_csv(resources: list[Resource]) -> str:
    """Export resources to CSV.

    Flattens metadata and tags into columns.

    Args:
        resources: List of Resource objects.

    Returns:
        CSV string.
    """
    if not resources:
        return ""

    # Collect all unique metadata and tag keys across all resources
    meta_keys: set[str] = set()
    tag_keys: set[str] = set()
    for r in resources:
        meta_keys.update(r.metadata.keys())
        tag_keys.update(r.tags.keys())

    meta_keys_sorted = sorted(meta_keys)
    tag_keys_sorted = sorted(tag_keys)

    # Build header
    base_fields = [
        "id", "name", "resource_type", "provider", "region",
        "state", "created_at",
    ]
    headers = (
        base_fields
        + [f"meta:{k}" for k in meta_keys_sorted]
        + [f"tag:{k}" for k in tag_keys_sorted]
    )

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(headers)

    for r in resources:
        row = [
            r.id,
            r.name,
            r.resource_type.value,
            r.provider,
            r.region,
            r.state.value,
            str(r.created_at) if r.created_at else "",
        ]
        row.extend(r.metadata.get(k, "") for k in meta_keys_sorted)
        row.extend(r.tags.get(k, "") for k in tag_keys_sorted)
        writer.writerow(row)

    return output.getvalue()


def to_yaml(resources: list[Resource]) -> str:
    """Export resources to YAML.

    Uses a simple serializer that doesn't require PyYAML.

    Args:
        resources: List of Resource objects.

    Returns:
        YAML string.
    """
    lines: list[str] = []
    for r in resources:
        d = _resource_to_dict(r)
        lines.append("- id: " + _yaml_val(d["id"]))
        lines.append("  name: " + _yaml_val(d["name"]))
        lines.append("  resource_type: " + _yaml_val(d["resource_type"]))
        lines.append("  provider: " + _yaml_val(d["provider"]))
        lines.append("  region: " + _yaml_val(d["region"]))
        lines.append("  state: " + _yaml_val(d["state"]))
        lines.append("  created_at: " + _yaml_val(d.get("created_at", "")))

        if d.get("tags"):
            lines.append("  tags:")
            for k, v in sorted(d["tags"].items()):
                lines.append(f"    {k}: {_yaml_val(v)}")

        if d.get("metadata"):
            lines.append("  metadata:")
            for k, v in sorted(d["metadata"].items()):
                if v:
                    lines.append(f"    {k}: {_yaml_val(v)}")

        lines.append("")

    return "\n".join(lines)


def _resource_to_dict(r: Resource) -> dict:
    """Convert a Resource to a plain dict for serialization."""
    return {
        "id": r.id,
        "name": r.name,
        "resource_type": r.resource_type.value,
        "provider": r.provider,
        "region": r.region,
        "state": r.state.value,
        "created_at": str(r.created_at) if r.created_at else None,
        "tags": dict(r.tags),
        "metadata": dict(r.metadata),
    }


def _yaml_val(v: object) -> str:
    """Format a value for YAML output."""
    if v is None:
        return "null"
    s = str(v)
    if not s:
        return '""'
    # Quote strings that could be misinterpreted
    if s in ("true", "false", "null", "yes", "no") or ":" in s or "#" in s:
        return f'"{s}"'
    return s
