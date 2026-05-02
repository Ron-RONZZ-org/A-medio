"""YouTube media service using yt-dlp."""

from __future__ import annotations

import json
import re
import shutil
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Generator

from A import error, info, tr, tr_multi
from A.core.service import CRUDService
from A.data.search import FTSConfig
from A.utils.normalize import fold_search_text

from A_medio.config import get_download_dir
from A_medio.services.base import MediaService
from A_medio.data.storage import get_db

if TYPE_CHECKING:
    from yt_dlp import YoutubeDL
    from yt_dlp.utils import DownloadError


# ──────────────────────────────────────────────────────────────────────────────
# Lazy imports for yt-dlp (avoids import overhead when not used)
# ──────────────────────────────────────────────────────────────────────────────

_ytdl_class: type[YoutubeDL] | None = None
_download_error_class: type[DownloadError] | None = None


def _get_ytdl_class() -> type[YoutubeDL]:
    """Lazy import ``yt_dlp.YoutubeDL``.

    Returns:
        The ``YoutubeDL`` class.
    """
    global _ytdl_class
    if _ytdl_class is None:
        from yt_dlp import YoutubeDL  # type: ignore[import-untyped]
        _ytdl_class = YoutubeDL
    return _ytdl_class


def _get_download_error() -> type[DownloadError]:
    """Lazy import ``yt_dlp.utils.DownloadError``.

    Returns:
        The ``DownloadError`` exception class.
    """
    global _download_error_class
    if _download_error_class is None:
        from yt_dlp.utils import DownloadError  # type: ignore[import-untyped]
        _download_error_class = DownloadError
    return _download_error_class


# ──────────────────────────────────────────────────────────────────────────────
# Format selector helpers
# ──────────────────────────────────────────────────────────────────────────────


def build_format_selector(
    resolution: int | None = None,
    audio_only: bool = False,
    video_only: bool = False,
    audio_bitrate: int | None = None,
) -> str:
    """Build a yt-dlp format selector string.

    Args:
        resolution: Max video height (e.g. 720, 1080). ``None`` means best.
        audio_only: If True, select best audio stream only.
        video_only: If True, select best video stream only (no audio).
        audio_bitrate: Max audio bitrate in kbps (only when ``audio_only``).

    Returns:
        A yt-dlp format string like ``"best[height<=1080]/best"``.

    Raises:
        ValueError: If both ``audio_only`` and ``video_only`` are True.
    """
    if audio_only and video_only:
        raise ValueError("Cannot use both audio-only and video-only.")

    if audio_only:
        if audio_bitrate is not None:
            return f"bestaudio[abr<={int(audio_bitrate)}]/bestaudio"
        return "bestaudio"

    if video_only:
        if resolution is not None:
            return f"bestvideo[height<={int(resolution)}]/bestvideo"
        return "bestvideo"

    if resolution is not None:
        return f"best[height<={int(resolution)}]/best"
    return "best"


def build_subtitle_opts(subtitles: str | None) -> dict[str, Any]:
    """Build yt-dlp options for subtitle downloading.

    Args:
        subtitles: Subtitle spec:
            - ``"auto"`` or ``"all"``: download all available subtitles.
            - Comma-separated language codes (e.g. ``"eo,en,fr"``).

    Returns:
        Dict of yt-dlp options, or empty dict if *subtitles* is falsy.
    """
    if not subtitles:
        return {}

    spec = subtitles.strip().lower()
    opts: dict[str, Any] = {
        "writesubtitles": True,
        "writeautomaticsub": spec in {"auto", "all"},
        "subtitlesformat": "best",
    }
    if spec not in {"auto", "all"}:
        langs = [x.strip() for x in subtitles.split(",") if x.strip()]
        if langs:
            opts["subtitleslangs"] = langs
    return opts


# ──────────────────────────────────────────────────────────────────────────────
# YtDlpWrapper — singleton with lazy import & availability detection
# ──────────────────────────────────────────────────────────────────────────────


class YtDlpWrapper:
    """Singleton wrapper around the yt-dlp Python library.

    Handles lazy import, availability detection, and provides a factory
    method for creating ``YoutubeDL`` context-manager instances.

    Usage::

        wrapper = YtDlpWrapper()
        if wrapper.is_available():
            with wrapper.create_ydl({"quiet": True}) as ydl:
                info = ydl.extract_info(url, download=False)
    """

    _instance: YtDlpWrapper | None = None
    _available: bool | None = None

    def __new__(cls) -> YtDlpWrapper:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    # ── availability ──────────────────────────────────────────────────────

    def is_available(self) -> bool:
        """Check whether yt-dlp is available.

        Checks for the ``yt-dlp`` CLI binary first, then tries importing
        the Python library.  The result is cached.

        Returns:
            True if yt-dlp can be used.
        """
        if self._available is None:
            # Check CLI binary first
            if shutil.which("yt-dlp") is not None:
                self._available = True
            else:
                # Fall back to Python library
                try:
                    import yt_dlp  # type: ignore[import-untyped]  # noqa: F401
                    self._available = True
                except ImportError:
                    self._available = False
        return self._available

    # ── factory ───────────────────────────────────────────────────────────

    @contextmanager
    def create_ydl(self, opts: dict[str, Any] | None = None) -> Generator[YoutubeDL, None, None]:
        """Create a ``YoutubeDL`` instance usable as a context manager.

        Args:
            opts: Options passed to the ``YoutubeDL`` constructor.

        Yields:
            A ``YoutubeDL`` instance.

        Raises:
            RuntimeError: If yt-dlp is not available.
        """
        if not self.is_available():
            raise RuntimeError("yt-dlp is not available")
        ydl = _get_ytdl_class()(opts or {})
        try:
            yield ydl
        finally:
            ydl.close()


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
        self._wrapper = YtDlpWrapper()

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
        return self._wrapper.is_available()

    def get_download_dir(self) -> str:
        """Return the configured download directory."""
        return get_download_dir()

    # ── search ────────────────────────────────────────────────────────────

    def _yt_dlp_search(self, query: str, limit: int = 10) -> list[YouTubeVideo]:
        """Search YouTube via yt-dlp Python library.

        Args:
            query: Search query string.
            limit: Max number of results.

        Returns:
            List of ``YouTubeVideo`` objects.
        """
        if not self.is_available():
            error(tr_multi(
                "yt-dlp ne estas instalita. Instalu ĝin por uzi serĉon.",
                "yt-dlp is not installed. Install it to use search.",
                "yt-dlp n'est pas installé. Installez-le pour utiliser la recherche.",
            ))
            return []

        opts: dict[str, Any] = {
            "quiet": True,
            "skip_download": True,
            "no_warnings": True,
            "ignoreerrors": True,
            "extract_flat": False,
        }
        search_query = f"ytsearch{max(1, limit)}:{query}"
        videos: list[YouTubeVideo] = []

        try:
            with self._wrapper.create_ydl(opts) as ydl:
                result = ydl.extract_info(search_query, download=False)
        except _get_download_error() as exc:
            error(tr_multi(
                f"Serĉo fiaskis: {exc}",
                f"Search failed: {exc}",
                f"Échec de recherche: {exc}",
            ))
            return []

        entries = result.get("entries") if isinstance(result, dict) else []
        for item in list(entries or []):
            if isinstance(item, dict):
                videos.append(YouTubeVideo.from_yt_dlp(item))
        return videos

    def search(
        self,
        query: str,
        **opts: Any,
    ) -> list[dict[str, Any]]:
        """Search YouTube for videos.

        Args:
            query: Search query string.
            **opts: Additional options:
                - limit: Max results (default 10).
                - filter: Field to filter on (title, description, author).
                - regex: Regex pattern to match.
                - playlist: Playlist URL to filter by.

        Returns:
            List of video dicts.
        """
        limit = opts.get("limit", 10)
        videos = self._yt_dlp_search(query, limit=limit)

        if not videos:
            return []

        # Store in database
        service = self.get_service()
        now = datetime.now().isoformat()
        for video in videos:
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

        results = [v.to_dict() for v in videos]

        if "filter" in opts and "regex" in opts:
            field = opts["filter"]
            pattern = opts["regex"]
            results = [r for r in results if self._regex_match(str(r.get(field, "")), pattern)]
        elif "regex" in opts:
            pattern = opts["regex"]
            results = [
                r for r in results
                if self._regex_match(r.get("title", ""), pattern)
                or self._regex_match(r.get("description", ""), pattern)
                or self._regex_match(r.get("author", ""), pattern)
            ]

        return results

    def _regex_match(self, text: str, pattern: str) -> bool:
        """Check if text matches regex pattern (case-insensitive)."""
        try:
            return bool(re.search(pattern, text, re.IGNORECASE))
        except re.error:
            return False

    # ── local cache ──────────────────────────────────────────────────────

    def get_by_id(self, video_id: str) -> dict[str, Any] | None:
        """Get a video by ID from local cache.

        Args:
            video_id: The YouTube video ID.

        Returns:
            Video dict or None.
        """
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
        return service.search_fts(query, **opts)

    # ── download ─────────────────────────────────────────────────────────

    def download(
        self,
        url: str,
        **opts: Any,
    ) -> list[Path]:
        """Download a YouTube video/audio.

        Args:
            url: YouTube URL to download.
            **opts: Download options:
                - output_dir: Output directory (default: from config).
                - resolution: Max video height (e.g. 720, 1080).
                - audio_only: Extract audio only.
                - video_only: Video stream only (no audio).
                - audio_bitrate: Max audio bitrate in kbps.
                - subtitles: Subtitle spec (auto, all, or langs).

        Returns:
            List of paths to downloaded files (empty if failed).
        """
        if not self.is_available():
            error(tr_multi(
                "yt-dlp ne estas instalita. Instalu ĝin por elŝuti.",
                "yt-dlp is not installed. Install it to download.",
                "yt-dlp n'est pas installé. Installez-le pour télécharger.",
            ))
            return []

        output_dir = Path(opts.get("output_dir", self.get_download_dir()))
        output_dir.mkdir(parents=True, exist_ok=True)

        format_sel = build_format_selector(
            resolution=opts.get("resolution"),
            audio_only=opts.get("audio_only", False),
            video_only=opts.get("video_only", False),
            audio_bitrate=opts.get("audio_bitrate"),
        )

        ydl_opts: dict[str, Any] = {
            "quiet": True,
            "no_warnings": True,
            "format": format_sel,
            "outtmpl": str(output_dir / "%(title).80s [%(id)s].%(ext)s"),
            "ignoreerrors": True,
        }
        ydl_opts.update(build_subtitle_opts(opts.get("subtitles")))

        before = {p for p in output_dir.iterdir()} if output_dir.exists() else set()

        try:
            with self._wrapper.create_ydl(ydl_opts) as ydl:
                ydl.extract_info(url, download=True)
        except _get_download_error() as exc:
            error(tr_multi(
                f"Elŝuto fiaskis: {exc}",
                f"Download failed: {exc}",
                f"Téléchargement échoué: {exc}",
            ))
            return []

        after = {p for p in output_dir.iterdir()}
        created = sorted(after - before, key=lambda p: p.name)

        if created:
            info(tr_multi(
                f"Elŝutis {len(created)} dosiero(j)n al {output_dir}",
                f"Downloaded {len(created)} file(s) to {output_dir}",
                f"Téléchargé {len(created)} fichier(s) vers {output_dir}",
            ))
        else:
            info(tr_multi(
                "Neniu dosiero elŝutita.",
                "No files downloaded.",
                "Aucun fichier téléchargé.",
            ))

        return created


# ──────────────────────────────────────────────────────────────────────────────
# Service singleton
# ──────────────────────────────────────────────────────────────────────────────

_service_instance: YouTubeService | None = None


def get_youtube_service() -> YouTubeService:
    """Get the YouTube service singleton.

    Returns:
        The shared ``YouTubeService`` instance.
    """
    global _service_instance
    if _service_instance is None:
        _service_instance = YouTubeService()
    return _service_instance


__all__ = [
    "YouTubeService",
    "YouTubeVideo",
    "YtDlpWrapper",
    "get_youtube_service",
    "build_format_selector",
    "build_subtitle_opts",
]
