"""YouTube media service using yt-dlp."""

from __future__ import annotations

import json
import shutil
from datetime import datetime
from typing import Any

from A import error, info, tr
from A.core.service import CRUDService
from A.data.search import FTSConfig
from A.utils.normalize import fold_search_text

from A_medio.services.base import MediaService
from A_medio.data.storage import get_db


# ──────────────────────────────────────────────────────────────────────────────
# YouTube video data structure
# ──────────────────────────────────────────────────────────────────────────────

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
    def from_yt_dlp(cls, data: dict[str, Any]) -> "YouTubeVideo":
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


# ──────────────────────────────────────────────────────────────────────────────
# YouTube service
# ──────────────────────────────────────────────────────────────────────────────

class YouTubeService(MediaService):
    """YouTube media service using yt-dlp."""

    _service: CRUDService | None = None

    def __init__(self) -> None:
        self._yt_dlp_path: str | None = None

    @classmethod
    def get_service(cls) -> CRUDService:
        """Get or create the CRUDService instance."""
        if cls._service is None:
            db = get_db()
            fts_config = FTSConfig(
                table="youtube_videos",
                fts_columns=["title", "description", "author"],
                filter_columns=["video_id", "author"],
                normalize={
                    "title": fold_search_text,
                    "description": fold_search_text,
                    "author": fold_search_text,
                },
            )
            cls._service = CRUDService(db, "youtube_videos", fts_config=fts_config)
        return cls._service

    def is_available(self) -> bool:
        """Check if yt-dlp is installed."""
        self._yt_dlp_path = shutil.which("yt-dlp")
        return self._yt_dlp_path is not None

    def _yt_dlp_search(self, query: str, limit: int = 10) -> list[YouTubeVideo]:
        """Run yt-dlp to search YouTube."""
        if not self.is_available():
            error(tr(
                "yt-dlp ne estas instalita. Instalu ĝin por uzi serĉon.",
                "yt-dlp is not installed. Install it to use search.",
                "yt-dlp n'est pas installé. Installez-le pour utiliser la recherche.",
            ))
            return []

        import subprocess

        cmd = [
            self._yt_dlp_path or "yt-dlp",
            "--quiet",
            "--print", "json",
            "--dump-json",
            f"ytsearch{limit}:{query}",
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True,
            )
            videos: list[YouTubeVideo] = []
            for line in result.stdout.strip().split("\n"):
                if line.strip():
                    data = json.loads(line)
                    videos.append(YouTubeVideo.from_yt_dlp(data))
            return videos
        except subprocess.CalledProcessError as e:
            error(tr(f"Serĉo fiaskis: {e.stderr}", f"Search failed: {e.stderr}", f"Échec de recherche: {e.stderr}"))
            return []
        except json.JSONDecodeError as e:
            error(tr(f"JSON decode error: {e}", f"JSON decode error: {e}", f"Erreur de décodage JSON: {e}"))
            return []

    def search(self, query: str, **opts: Any) -> list[dict[str, Any]]:
        """Search YouTube for videos.

        Args:
            query: Search query string.
            **opts: Additional options:
                - limit: Max results (default 10)
                - filter: Field to filter on (title, description, author)
                - regex: Regex pattern to match
                - playlist: Playlist URL to filter by

        Returns:
            List of video dicts.
        """
        limit = opts.get("limit", 10)

        # Fetch from YouTube
        videos = self._yt_dlp_search(query, limit=limit)

        if not videos:
            return []

        # Store in database
        service = self.get_service()
        now = datetime.now().isoformat()

        for video in videos:
            # Check if already exists
            existing = service.get_by_filter(video_id=video.video_id)
            if not existing:
                service.create({
                    "video_id": video.video_id,
                    "title": video.title,
                    "description": video.description,
                    "author": video.author,
                    "duration": video.duration,
                    "view_count": video.view_count,
                    "upload_date": video.upload_date,
                    "thumbnail_url": video.thumbnail_url,
                    "url": video.url,
                    "kreita_je": now,
                    "modifita_je": now,
                })

        # Apply local filters if specified
        results = [v.to_dict() for v in videos]

        if "filter" in opts and "regex" in opts:
            # Complex filter: field + regex
            field = opts["filter"]
            pattern = opts["regex"]
            results = [r for r in results if self._regex_match(str(r.get(field, "")), pattern)]
        elif "regex" in opts:
            # Search all text fields with regex
            pattern = opts["regex"]
            results = [
                r for r in results
                if self._regex_match(r.get("title", ""), pattern)
                or self._regex_match(r.get("description", ""), pattern)
                or self._regex_match(r.get("author", ""), pattern)
            ]

        return results

    def _regex_match(self, text: str, pattern: str) -> bool:
        """Check if text matches regex pattern."""
        import re
        try:
            return bool(re.search(pattern, text, re.IGNORECASE))
        except re.error:
            return False

    def get_by_id(self, video_id: str) -> dict[str, Any] | None:
        """Get a video by ID from local cache."""
        service = self.get_service()
        result = service.get_by_filter(video_id=video_id)
        return result[0] if result else None

    def search_local(self, query: str, **opts: Any) -> list[dict[str, Any]]:
        """Search local cache only (using FTS5).

        Args:
            query: Search query string.
            **opts: Additional options passed to FTS search.

        Returns:
            List of video dicts from local cache.
        """
        service = self.get_service()
        results = service.search_fts(query, **opts)
        return results


# ──────────────────────────────────────────────────────────────────────────────
# Service singleton
# ──────────────────────────────────────────────────────────────────────────────

_service_instance: YouTubeService | None = None


def get_youtube_service() -> YouTubeService:
    """Get the YouTube service singleton."""
    global _service_instance
    if _service_instance is None:
        _service_instance = YouTubeService()
    return _service_instance


__all__ = ["YouTubeService", "YouTubeVideo", "get_youtube_service"]