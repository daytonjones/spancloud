"""Mock provider package — static demo data for screenshots and demos."""

from __future__ import annotations

from spancloud.providers.mock.provider import MockProvider

_MOCK_SPECS = [
    ("aws",          "Amazon Web Services"),
    ("gcp",          "Google Cloud Platform"),
    ("azure",        "Microsoft Azure"),
    ("digitalocean", "DigitalOcean"),
    ("vultr",        "Vultr"),
    ("oci",          "Oracle Cloud"),
    ("alibaba",      "Alibaba Cloud"),
]


def build_mock_providers() -> list[MockProvider]:
    """Return one MockProvider per cloud, with realistic demo data."""
    return [MockProvider(name, display) for name, display in _MOCK_SPECS]
