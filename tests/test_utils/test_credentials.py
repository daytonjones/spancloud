"""Tests for the secure credential store — file-fallback path."""

from __future__ import annotations

from pathlib import Path  # noqa: TC003 — used at runtime by pytest fixtures

import pytest


@pytest.fixture
def isolated_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect the spancloud config dir to a tmp path and force the file backend."""
    from spancloud.config import get_settings

    monkeypatch.setattr(
        get_settings().__class__,
        "ensure_config_dir",
        lambda self: tmp_path,
    )

    # Force the file-fallback path by making the keyring ops fail
    from spancloud.utils import credentials

    monkeypatch.setattr(credentials, "_save_keyring", lambda p, k, v: False)
    monkeypatch.setattr(credentials, "_load_keyring", lambda p, k: None)
    monkeypatch.setattr(credentials, "_delete_keyring", lambda p, k: False)

    return tmp_path


class TestFileFallback:
    def test_save_and_load(self, isolated_config: Path) -> None:
        from spancloud.utils import credentials

        assert credentials.save("vultr", "api_key", "SECRET_123") is True
        assert credentials.load("vultr", "api_key") == "SECRET_123"

    def test_load_missing_returns_none(self, isolated_config: Path) -> None:
        from spancloud.utils import credentials

        assert credentials.load("vultr", "api_key") is None

    def test_delete(self, isolated_config: Path) -> None:
        from spancloud.utils import credentials

        credentials.save("digitalocean", "token", "TOK")
        assert credentials.load("digitalocean", "token") == "TOK"

        assert credentials.delete("digitalocean", "token") is True
        assert credentials.load("digitalocean", "token") is None

    def test_delete_missing_returns_false(self, isolated_config: Path) -> None:
        from spancloud.utils import credentials

        assert credentials.delete("vultr", "api_key") is False

    def test_multiple_providers_isolated(self, isolated_config: Path) -> None:
        from spancloud.utils import credentials

        credentials.save("vultr", "api_key", "VULTR_KEY")
        credentials.save("digitalocean", "token", "DO_TOKEN")

        assert credentials.load("vultr", "api_key") == "VULTR_KEY"
        assert credentials.load("digitalocean", "token") == "DO_TOKEN"

        credentials.delete("vultr", "api_key")

        assert credentials.load("vultr", "api_key") is None
        assert credentials.load("digitalocean", "token") == "DO_TOKEN"

    def test_overwrite(self, isolated_config: Path) -> None:
        from spancloud.utils import credentials

        credentials.save("vultr", "api_key", "OLD")
        credentials.save("vultr", "api_key", "NEW")
        assert credentials.load("vultr", "api_key") == "NEW"

    def test_ciphertext_not_readable_as_plaintext(
        self, isolated_config: Path
    ) -> None:
        """The stored file must not contain the plaintext token."""
        from spancloud.utils import credentials

        credentials.save("vultr", "api_key", "VERY_SECRET_VALUE_12345")
        path = isolated_config / "credentials.enc"
        assert path.exists()
        contents = path.read_bytes()
        assert b"VERY_SECRET_VALUE_12345" not in contents

    def test_key_file_has_restrictive_mode(self, isolated_config: Path) -> None:
        """The Fernet key file must be mode 0600."""
        import stat

        from spancloud.utils import credentials

        credentials.save("vultr", "api_key", "x")
        key_path = isolated_config / ".cred_key"
        assert key_path.exists()
        mode = key_path.stat().st_mode & 0o777
        # Owner read/write only (0600) — no group/other access
        assert mode & stat.S_IRWXG == 0
        assert mode & stat.S_IRWXO == 0
