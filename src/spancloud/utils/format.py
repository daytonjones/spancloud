"""Shared formatting helpers."""

from __future__ import annotations


def format_size(size_bytes: int) -> str:
    """Convert a byte count to a human-readable string (KB / MB / GB)."""
    if size_bytes > 1_073_741_824:
        return f"{size_bytes / 1_073_741_824:,.2f} GB"
    if size_bytes > 1_048_576:
        return f"{size_bytes / 1_048_576:,.2f} MB"
    if size_bytes > 0:
        return f"{size_bytes / 1024:,.2f} KB"
    return "0 B"
