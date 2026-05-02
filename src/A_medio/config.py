"""Plugin-level configuration for A-medio.

Wraps ``A.core.config`` with a ``"A-medio."`` namespace prefix,
so all settings are stored under ``[A.settings]`` in the global
``~/.config/A/config.toml``.
"""

from __future__ import annotations

from typing import Any

from A.core.config import get_setting as _core_get
from A.core.config import set_setting as _core_set
from A.core.paths import data_dir

__all__ = [
    "get_setting",
    "set_setting",
    "get_download_dir",
    "set_download_dir",
]

_PREFIX = "A-medio."


# ──────────────────────────────────────────────────────────────────────────────
# Generic namespaced accessors
# ──────────────────────────────────────────────────────────────────────────────


def get_setting(key: str, default: Any = None) -> Any:
    """Read a namespaced plugin setting.

    Args:
        key: Setting name (the ``"A-medio."`` prefix is added automatically).
        default: Value returned when the key is missing.

    Returns:
        The stored value, or *default*.
    """
    return _core_get(_PREFIX + key, default)


def set_setting(key: str, value: Any) -> None:
    """Write a namespaced plugin setting.

    Persisted to ``[A.settings]`` in ``~/.config/A/config.toml``.

    Args:
        key: Setting name (the ``"A-medio."`` prefix is added automatically).
        value: Value to store.  Must be TOML-serialisable (str, bool,
            int, float, list, dict).
    """
    _core_set(_PREFIX + key, value)


# ──────────────────────────────────────────────────────────────────────────────
# Typed convenience accessors
# ──────────────────────────────────────────────────────────────────────────────


def get_download_dir() -> str:
    """Return the default download directory path.

    Defaults to ``<data_dir>/filmetoj``.
    """
    default = str(data_dir() / "filmetoj")
    return get_setting("download_dir", default)


def set_download_dir(path: str) -> None:
    """Set the default download directory.

    Args:
        path: Absolute path to the download folder.
    """
    set_setting("download_dir", path)
