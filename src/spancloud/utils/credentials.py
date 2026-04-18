"""Secure credential storage for provider API tokens.

Provides a simple save/load/delete API backed by the OS keyring where
available (macOS Keychain, Linux Secret Service, Windows Credential Locker).
Falls back to a Fernet-encrypted file at ~/.config/skyforge/credentials.enc
when no keyring backend is present (headless Linux, minimal containers).

Usage:
    from skyforge.utils.credentials import save, load, delete

    save("vultr", "api_key", "ABC123...")
    token = load("vultr", "api_key")          # returns None if not found
    delete("vultr", "api_key")                # returns True if removed
"""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path  # noqa: TC003 — used at runtime

from skyforge.config import get_settings
from skyforge.utils.logging import get_logger

logger = get_logger(__name__)

_SERVICE_PREFIX = "skyforge"
_FALLBACK_FILE = "credentials.enc"
_FALLBACK_KEY_FILE = ".cred_key"


def save(provider: str, key: str, value: str) -> bool:
    """Store a credential under (provider, key).

    Tries the OS keyring first; falls back to an encrypted file.

    Returns:
        True on success, False otherwise.
    """
    if _save_keyring(provider, key, value):
        return True
    return _save_file(provider, key, value)


def load(provider: str, key: str) -> str | None:
    """Load a previously saved credential, or None if not found."""
    value = _load_keyring(provider, key)
    if value is not None:
        return value
    return _load_file(provider, key)


def delete(provider: str, key: str) -> bool:
    """Delete a stored credential. Returns True if something was removed."""
    removed = False
    if _delete_keyring(provider, key):
        removed = True
    if _delete_file(provider, key):
        removed = True
    return removed


def backend_name() -> str:
    """Return a human-readable name for the active storage backend."""
    try:
        import keyring

        backend = keyring.get_keyring()
        cls = type(backend)
        module = cls.__module__
        # The "null" fallback backend lives in keyring.backends.fail
        if module.endswith("backends.fail") or module.endswith("backends.null"):
            if _file_store_exists():
                return "encrypted file (~/.config/skyforge/credentials.enc)"
            return "none (no usable keyring backend)"
        # Friendly names for the common OS backends
        friendly = {
            "keyring.backends.macOS": "macOS Keychain",
            "keyring.backends.Windows": "Windows Credential Locker",
            "keyring.backends.SecretService": "Linux Secret Service",
            "keyring.backends.kwallet": "KDE KWallet",
            "keyring.backends.chainer": "chained keyring",
        }
        label = friendly.get(module, f"{module}.{cls.__name__}")
        return f"OS keyring ({label})"
    except Exception:
        if _file_store_exists():
            return "encrypted file (~/.config/skyforge/credentials.enc)"
        return "none"


# ---------------------------------------------------------------------------
# Keyring backend
# ---------------------------------------------------------------------------


def _service_name(provider: str) -> str:
    return f"{_SERVICE_PREFIX}.{provider}"


def _save_keyring(provider: str, key: str, value: str) -> bool:
    try:
        import keyring
        from keyring.errors import KeyringError

        keyring.set_password(_service_name(provider), key, value)
        return True
    except (KeyringError, Exception) as exc:
        logger.debug("Keyring save failed (%s); will try file fallback", exc)
        return False


def _load_keyring(provider: str, key: str) -> str | None:
    try:
        import keyring
        from keyring.errors import KeyringError

        return keyring.get_password(_service_name(provider), key)
    except (KeyringError, Exception) as exc:
        logger.debug("Keyring load failed (%s); will try file fallback", exc)
        return None


def _delete_keyring(provider: str, key: str) -> bool:
    try:
        import keyring
        from keyring.errors import KeyringError, PasswordDeleteError

        try:
            keyring.delete_password(_service_name(provider), key)
            return True
        except PasswordDeleteError:
            return False
    except (KeyringError, Exception) as exc:
        logger.debug("Keyring delete failed (%s)", exc)
        return False


# ---------------------------------------------------------------------------
# Encrypted-file fallback
# ---------------------------------------------------------------------------


def _config_dir() -> Path:
    return get_settings().ensure_config_dir()


def _key_path() -> Path:
    return _config_dir() / _FALLBACK_KEY_FILE


def _file_path() -> Path:
    return _config_dir() / _FALLBACK_FILE


def _file_store_exists() -> bool:
    return _file_path().exists()


def _load_or_create_fernet() -> object:
    """Load the Fernet symmetric key from disk, creating it if missing."""
    from cryptography.fernet import Fernet

    key_path = _key_path()
    if key_path.exists():
        raw = key_path.read_bytes().strip()
    else:
        raw = Fernet.generate_key()
        key_path.write_bytes(raw)
        # Owner-read only
        os.chmod(key_path, stat.S_IRUSR | stat.S_IWUSR)
    return Fernet(raw)


def _read_store() -> dict[str, dict[str, str]]:
    """Return the decrypted credential store as a nested dict."""
    path = _file_path()
    if not path.exists():
        return {}
    try:
        fernet = _load_or_create_fernet()
        ciphertext = path.read_bytes()
        plaintext = fernet.decrypt(ciphertext)
        data = json.loads(plaintext.decode("utf-8"))
        if isinstance(data, dict):
            return data
    except Exception as exc:
        logger.warning("Could not decrypt credentials file: %s", exc)
    return {}


def _write_store(data: dict[str, dict[str, str]]) -> bool:
    """Write the store back to disk, encrypted."""
    try:
        fernet = _load_or_create_fernet()
        plaintext = json.dumps(data).encode("utf-8")
        ciphertext = fernet.encrypt(plaintext)
        path = _file_path()
        path.write_bytes(ciphertext)
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
        return True
    except Exception as exc:
        logger.warning("Could not write credentials file: %s", exc)
        return False


def _save_file(provider: str, key: str, value: str) -> bool:
    store = _read_store()
    store.setdefault(provider, {})[key] = value
    return _write_store(store)


def _load_file(provider: str, key: str) -> str | None:
    store = _read_store()
    return store.get(provider, {}).get(key)


def _delete_file(provider: str, key: str) -> bool:
    store = _read_store()
    if provider in store and key in store[provider]:
        del store[provider][key]
        if not store[provider]:
            del store[provider]
        _write_store(store)
        return True
    return False
