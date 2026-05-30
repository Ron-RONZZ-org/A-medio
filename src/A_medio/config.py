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
    "get_cookies_from_browser",
    "set_cookies_from_browser",
    "get_cookies_from_browser_profile",
]

_DEFAULT_DOWNLOAD_DIR = str(data_dir() / "filmetoj")

_schema = ConfigSchema("A-medio", {
    "download_dir": {
        "type": "str",
        "default": _DEFAULT_DOWNLOAD_DIR,
        "help": "Default download directory",
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


def get_cookies_from_browser() -> str | None:
    """Return the saved browser name for auto cookie extraction.

    Returns:
        Browser name (floorp, firefox, etc.) or ``None`` if not set.
    """
    return get_setting("cookies_from_browser")


def set_cookies_from_browser(browser: str | None, profile: str | None = None) -> None:
    """Save the browser (and optional profile) for auto cookie extraction.

    Args:
        browser: Browser name (floorp, firefox, etc.) or ``None`` to clear.
        profile: Optional specific profile path. When ``None``, yt-dlp auto-selects.
    """
    set_setting("cookies_from_browser", browser)
    set_setting("cookies_from_browser_profile", profile)


def get_cookies_from_browser_profile() -> str | None:
    """Return the saved browser profile path for cookie extraction.

    Returns:
        Profile directory path, or ``None`` if not set.
    """
    return get_setting("cookies_from_browser_profile")
