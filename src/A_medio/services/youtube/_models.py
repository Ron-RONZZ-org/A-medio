"""Data models for YouTube service."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class YouTubeVideo:
    """YouTube video data."""

    def __init__(
        self,
        video_id: str,
        title: str,
        description: str = "",
        author: str = "",
        duration: int = 0,
        view_count: int = 0,
        upload_date: str = "",
        thumbnail_url: str = "",
        url: str = "",
    ) -> None:
        self.video_id = video_id
        self.title = title
        self.description = description
        self.author = author
        self.duration = duration
        self.view_count = view_count
        self.upload_date = upload_date
        self.thumbnail_url = thumbnail_url
        self.url = url or f"https://www.youtube.com/watch?v={video_id}"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for storage."""
        return {
            "video_id": self.video_id,
            "title": self.title,
            "description": self.description,
            "author": self.author,
            "duration": self.duration,
            "view_count": self.view_count,
            "upload_date": self.upload_date,
            "thumbnail_url": self.thumbnail_url,
            "url": self.url,
        }

    @classmethod
    def from_yt_dlp(cls, data: dict[str, Any]) -> YouTubeVideo:
        """Create YouTubeVideo from yt-dlp JSON output."""
        return cls(
            video_id=data.get("id", ""),
            title=data.get("title", ""),
            description=data.get("description", ""),
            author=data.get("uploader", ""),
            duration=data.get("duration", 0),
            view_count=data.get("view_count", 0),
            upload_date=data.get("upload_date", ""),
            thumbnail_url=data.get("thumbnail", ""),
            url=data.get("webpage_url", ""),
        )


@dataclass
class BatchResult:
    """Result of a single batch-download operation."""

    row: int
    url: str
    success: bool
    files: list[Path] = field(default_factory=list)
    error: str | None = None


@dataclass
class EstimateResult:
    """Result of a download size estimation."""

    count: int
    total_bytes: int
    items: list[dict[str, Any]] = field(default_factory=list)

    @property
    def total_size_str(self) -> str:
        """Human-readable total size."""
        return _format_size(self.total_bytes)


def _format_size(num_bytes: int) -> str:
    """Format byte count to a human-readable string.

    Args:
        num_bytes: Size in bytes.

    Returns:
        e.g. ``"150.2 MB"``, ``"1.5 GB"``, or ``"--"`` for zero.
    """
    if num_bytes <= 0:
        return "--"
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024.0:
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} PB"
