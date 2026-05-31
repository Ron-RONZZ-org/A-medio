"""YouTube media service using yt-dlp.

Re-exports all public symbols from the sub-modules for backward compatibility.
"""

from __future__ import annotations

from A_medio.config import get_download_dir
from A_medio.services.youtube._wrapper import YtDlpWrapper, auto_js_runtimes, get_download_error
from A_medio.services.youtube._models import YouTubeVideo, BatchResult, EstimateResult
from A_medio.services.youtube._format_helpers import build_format_selector, build_subtitle_opts
from A_medio.services.youtube._cookie_helpers import (
    build_cookie_opts,
    _cookie_browser_candidates,
    _cookie_help_text,
    _detect_available_browsers,
    _parse_cookies_from_browser,
)
from A_medio.services.youtube._csv_helpers import parse_csv_rows
from A_medio.services.youtube._strategy import _save_search_strategy, _load_search_strategy
from A_medio.services.youtube.service import YouTubeService, get_youtube_service

# Backward-compat alias — old name used in tests
_get_download_error = get_download_error

__all__ = [
    "YouTubeService",
    "YouTubeVideo",
    "YtDlpWrapper",
    "BatchResult",
    "EstimateResult",
    "get_youtube_service",
    "get_download_dir",
    "build_format_selector",
    "build_subtitle_opts",
    "build_cookie_opts",
    "parse_csv_rows",
    "_cookie_help_text",
    "_cookie_browser_candidates",
    "_detect_available_browsers",
    "_parse_cookies_from_browser",
    "_save_search_strategy",
    "_load_search_strategy",
    "_get_download_error",
]
