"""A-medio — video, photo, audio management."""

from A_medio.cli import app
from A_medio.config import get_download_dir, get_setting, set_download_dir, set_setting

__all__ = [
    "app",
    "get_download_dir",
    "set_download_dir",
    "get_setting",
    "set_setting",
]
