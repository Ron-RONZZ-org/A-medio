"""YouTube media service using yt-dlp.

Re-exports all public symbols from the sub-modules for backward compatibility.
"""

from __future__ import annotations

from A_medio.services.youtube._wrapper import YtDlpWrapper
from A_medio.services.youtube._models import YouTubeVideo, BatchResult, EstimateResult
from A_medio.services.youtube._format_helpers import build_format_selector, build_subtitle_opts
from A_medio.services.youtube._cookie_helpers import build_cookie_opts, _cookie_help_text
from A_medio.services.youtube._csv_helpers import parse_csv_rows
from A_medio.services.youtube.service import YouTubeService, get_youtube_service

__all__ = [
    "YouTubeService",
    "YouTubeVideo",
    "YtDlpWrapper",
    "BatchResult",
    "EstimateResult",
    "get_youtube_service",
    "build_format_selector",
    "build_subtitle_opts",
    "build_cookie_opts",
    "parse_csv_rows",
    "_cookie_help_text",
]
