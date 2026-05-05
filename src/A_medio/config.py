"""Plugin-level configuration for A-medio.

Uses ``A.core.config.ConfigSchema`` for per-module config storage.
TOML path: ``~/.config/A/A-medio/config.toml``
"""

from __future__ import annotations

from typing import Any

from A.core.config import ConfigSchema
from A.core.paths import data_dir

__all__ = [
    "get_setting",
    "set_setting",
    "get_download_dir",
    "set_download_dir",
]

_DEFAULT_DOWNLOAD_DIR = str(data_dir() / "filmetoj")

_schema = ConfigSchema("A-medio", {
    "download_dir": {
        "type": "str",
        "default": _DEFAULT_DOWNLOAD_DIR,
        "help": "Default download directory",
    },
})


def get_setting(key: str, default: Any = None) -> Any:
    """Read a plugin setting from per-module TOML config.

    Args:
        key: Setting name.
        default: Value returned when the key is missing.

    Returns:
        The stored value, or *default*.
    """
    cfg = _schema.load()
    return cfg.get(key, default)


def set_setting(key: str, value: Any) -> None:
    """Write a plugin setting to per-module TOML config.

    Persisted to ``~/.config/A/A-medio/config.toml``.

    Args:
        key: Setting name.
        value: Value to store.  Must be TOML-serialisable (str, bool,
            int, float, list, dict).
    """
    cfg = _schema.load()
    cfg[key] = value
    _schema.save(cfg)


def get_download_dir() -> str:
    """Return the default download directory path.

    Defaults to ``<data_dir>/filmetoj``.
    """
    return get_setting("download_dir", _schema.default("download_dir"))


def set_download_dir(path: str) -> None:
    """Set the default download directory.

    Args:
        path: Absolute path to the download folder.
    """
    set_setting("download_dir", path)
