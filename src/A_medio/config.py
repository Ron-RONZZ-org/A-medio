"""Plugin-level configuration for A-medio.

Reads from ``[filmeto]`` section in the central config
(``~/.config/A/config.toml``) or falls back to ``[A.settings]`` dot-notation
and finally the legacy per-module TOML.
"""

from __future__ import annotations

from typing import Any

from A.core.config import get_module_setting, set_module_setting, ConfigSchema, register_module_defaults
from A.core.paths import data_dir

# Register filmeto defaults so they appear as commented keys in config.toml
register_module_defaults("filmeto", {
    "default_output":         (str(data_dir() / "filmetoj"), "Default download directory"),
    "cookies_from_browser":   ("", "Browser name for cookie extraction (floorp, firefox)"),
    "cookies_from_browser_profile": ("", "Specific browser profile path for cookies"),
})

__all__ = [
    "get_setting",
    "set_setting",
    "get_download_dir",
    "set_download_dir",
    "get_cookies_from_browser",
    "set_cookies_from_browser",
    "get_cookies_from_browser_profile",
]

# Legacy per-module schema (fallback for existing installs)
_legacy_schema = ConfigSchema("A-medio", {
    "download_dir": {
        "type": "str",
        "default": None,
        "help": "Default download directory (computed from data_dir dynamically)",
    },
    "cookies_from_browser": {
        "type": "str",
        "default": None,
        "help": "Browser name for auto cookie extraction (floorp, firefox, etc.)",
    },
    "cookies_from_browser_profile": {
        "type": "str",
        "default": None,
        "help": "Specific browser profile path for cookie extraction",
    },
})

_MODULE = "filmeto"
_SENTINEL = object()


def _read_legacy(key: str, default: Any = None) -> Any:
    """Fallback: read from legacy per-module TOML if central config absent."""
    central = get_module_setting(_MODULE, key, _SENTINEL)
    if central is not _SENTINEL:
        return central
    cfg = _legacy_schema.load()
    return cfg.get(key, default)


def get_setting(key: str, default: Any = None) -> Any:
    """Read a plugin setting from central config (or legacy).

    Checks ``[filmeto]`` in ``~/.config/A/config.toml`` first, then
    falls back to ``[A.settings]`` dot-notation and legacy per-module TOML.

    Args:
        key: Setting name (e.g. ``"default_output"``).
        default: Value returned when the key is missing.

    Returns:
        The stored value, or *default*.
    """
    return _read_legacy(key, default)


def set_setting(key: str, value: Any) -> None:
    """Write a plugin setting to the ``[filmeto]`` section.

    Persisted to ``[filmeto]`` in ``~/.config/A/config.toml``.
    Cleans up any legacy keys with the same name.

    Args:
        key: Setting name.
        value: Value to store (must be TOML-serialisable).
    """
    set_module_setting(_MODULE, key, value)


def get_download_dir() -> str:
    """Return the default download directory path.

    Reads ``default_output`` from ``[filmeto]`` section.
    Falls back to legacy ``download_dir``, then ``<data_dir>/filmetoj``.
    """
    central = get_module_setting(_MODULE, "default_output", _SENTINEL)
    if central is not _SENTINEL:
        return central
    legacy = _legacy_schema.load().get("download_dir")
    if legacy is not None:
        return legacy
    return str(data_dir() / "filmetoj")


def set_download_dir(path: str) -> None:
    """Set the default download directory (writes to ``[filmeto]``).

    Args:
        path: Absolute path to the download folder.
    """
    set_module_setting(_MODULE, "default_output", path)


def get_cookies_from_browser() -> str | None:
    """Return the saved browser name for auto cookie extraction.

    Returns:
        Browser name (floorp, firefox, etc.) or ``None`` if not set.
    """
    return _read_legacy("cookies_from_browser")


def set_cookies_from_browser(browser: str | None, profile: str | None = None) -> None:
    """Save the browser (and optional profile) for auto cookie extraction.

    Args:
        browser: Browser name (floorp, firefox, etc.) or ``None`` to clear.
        profile: Optional specific profile path.
    """
    set_module_setting(_MODULE, "cookies_from_browser", browser)
    set_module_setting(_MODULE, "cookies_from_browser_profile", profile)


def get_cookies_from_browser_profile() -> str | None:
    """Return the saved browser profile path for cookie extraction.

    Returns:
        Profile directory path, or ``None`` if not set.
    """
    return _read_legacy("cookies_from_browser_profile")
