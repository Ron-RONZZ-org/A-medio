"""YouTube media service using yt-dlp."""

from __future__ import annotations

import csv
import json
import re
import shutil
from contextlib import contextmanager
from dataclasses import dataclass, field
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
# CSV batch download support
# ──────────────────────────────────────────────────────────────────────────────

# Mapping of CSV column headers → internal option keys.
# Esperanto names preferred; English aliases accepted.
_CSV_HEADER_MAP: dict[str, str] = {
    # targets (required)
    "celoj": "targets",
    "targets": "targets",
    "target": "targets",
    "url": "targets",
    "urls": "targets",
    # resolution
    "difino": "resolution",
    "rezolucio": "resolution",
    "resolution": "resolution",
    # audio bitrate
    "sonkvalito": "audio_bitrate",
    "audio_bitrate": "audio_bitrate",
    "bitrate": "audio_bitrate",
    # bool flags
    "audio": "audio_only",
    "filmeto": "video_only",
    "video_only": "video_only",
    # output directory
    "vojo": "output_dir",
    "output_dir": "output_dir",
    "output": "output_dir",
    "path": "output_dir",
    "directory": "output_dir",
    # subtitles
    "subtitoloj": "subtitles",
    "subtitles": "subtitles",
    "subs": "subtitles",
}

_CSV_TRUE_VALUES: frozenset[str] = frozenset({"1", "true", "yes", "y", "jes", "j"})
_CSV_FALSE_VALUES: frozenset[str] = frozenset({"0", "false", "no", "n", "ne"})


def _csv_effective_cell(raw: object) -> str | None:
    """Return stripped text or ``None`` for empty/null cells."""
    text = str(raw or "").strip()
    if not text:
        return None
    if text.lower() in {"null", "none", "nil"}:
        return None
    return text


def _normalize_csv_header(raw: str) -> str | None:
    """Normalise a CSV column header to an internal option key.

    Args:
        raw: Raw header string.

    Returns:
        Internal key name, or ``None`` if unrecognised.
    """
    key = raw.strip().lower().replace("-", "_").replace(" ", "_")
    return _CSV_HEADER_MAP.get(key)


def _parse_csv_bool(value: str, *, field: str, row: int) -> bool:
    """Parse a CSV cell as a boolean.

    Args:
        value: Cell text.
        field: Field name (for error messages).
        row: Row number (for error messages, 1-indexed).

    Returns:
        True or False.

    Raises:
        ValueError: If value is not a recognised boolean.
    """
    normalized = value.strip().lower()
    if normalized in _CSV_TRUE_VALUES:
        return True
    if normalized in _CSV_FALSE_VALUES:
        return False
    raise ValueError(
        f"CSV vico {row}: nevalida valoro por '{field}': {value!r}. "
        f"Uzu jes/ne aŭ true/false."
    )


def parse_csv_rows(
    csv_path: str | Path,
    initial_state: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Parse a CSV file into a list of download specs.

    The CSV **must** have a ``celoj`` (targets) column.  Each row
    specifies download options; empty cells inherit from the previous
    row (or from *initial_state* for the first row).

    Supported columns (Esperanto / English):

    ==============  =======================  ===========
    Header          Key                      Type
    ==============  =======================  ===========
    ``celoj``       ``targets``              URL string(s)
    ``difino``      ``resolution``           int
    ``sonkvalito``  ``audio_bitrate``        int
    ``audio``       ``audio_only``           bool
    ``filmeto``     ``video_only``           bool
    ``vojo``        ``output_dir``           str
    ``subtitoloj``  ``subtitles``            str
    ==============  =======================  ===========

    Args:
        csv_path: Path to the CSV file.
        initial_state: Default values inherited by all rows.

    Returns:
        List of download-spec dicts, each with at least a ``"targets"`` key.

    Raises:
        FileNotFoundError: If the CSV file does not exist.
        ValueError: If required columns are missing or cell parsing fails.
    """
    path = Path(csv_path)
    if not path.exists():
        raise FileNotFoundError(f"CSV-dosiero ne trovita: {path}")

    state: dict[str, Any] = dict(initial_state or {})
    rows: list[dict[str, Any]] = []

    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        headers = list(reader.fieldnames or [])
        if not headers:
            raise ValueError("CSV-dosiero estas malplena (neniu kaprubriko).")

        # Map headers to internal keys
        mapped: dict[str, str] = {}
        for header in headers:
            key = _normalize_csv_header(header)
            if key:
                mapped[header] = key

        if "targets" not in mapped.values():
            raise ValueError(
                "CSV-dosiero devas havi kolumnon 'celoj' (URL-oj). "
                f"Trovitaj: {', '.join(headers)}"
            )

        for row_number, row in enumerate(reader, start=2):
            if not isinstance(row, dict):
                continue

            for raw_header, option_key in mapped.items():
                cell = _csv_effective_cell(row.get(raw_header))
                if cell is None:
                    continue

                if option_key == "targets":
                    # Split on whitespace, comma, or semicolon
                    targets = [
                        t for t in re.split(r"[\s,;]+", cell) if t
                    ]
                    if not targets:
                        raise ValueError(
                            f"CSV vico {row_number}: malplena 'celoj'."
                        )
                    state["targets"] = targets

                elif option_key in {"audio_only", "video_only"}:
                    state[option_key] = _parse_csv_bool(
                        cell, field=option_key, row=row_number,
                    )

                elif option_key in {"resolution", "audio_bitrate"}:
                    try:
                        state[option_key] = int(cell)
                    except ValueError as exc:
                        raise ValueError(
                            f"CSV vico {row_number}: nevalida nombro por "
                            f"'{option_key}': {cell!r}."
                        ) from exc

                elif option_key in {"output_dir", "subtitles"}:
                    state[option_key] = cell

            # Ensure targets exist
            targets = state.get("targets")
            if not isinstance(targets, list) or not targets:
                raise ValueError(
                    f"CSV vico {row_number}: mankas valida 'celoj'."
                )

            rows.append({
                "targets": list(targets),
                "resolution": state.get("resolution"),
                "audio_bitrate": state.get("audio_bitrate"),
                "audio_only": bool(state.get("audio_only", False)),
                "video_only": bool(state.get("video_only", False)),
                "output_dir": state.get("output_dir"),
                "subtitles": state.get("subtitles"),
            })

    return rows


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
# Batch download result
# ──────────────────────────────────────────────────────────────────────────────


@dataclass
class BatchResult:
    """Result of a single batch-download operation.

    Attributes:
        row: Row number in the input (1-indexed).
        url: The URL that was downloaded.
        success: Whether the download succeeded.
        files: List of paths to downloaded files.
        error: Error message if *success* is False.
    """

    row: int
    url: str
    success: bool
    files: list[Path] = field(default_factory=list)
    error: str | None = None


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

    def batch_download(
        self,
        specs: list[dict[str, Any]],
    ) -> list[BatchResult]:
        """Download multiple items from a list of download specs.

        Each spec should contain at least ``"targets"`` (list of URLs).
        Other keys are forwarded to :meth:`download` as ``**opts``.

        Args:
            specs: List of download-spec dicts (e.g. from :func:`parse_csv_rows`).

        Returns:
            List of :class:`BatchResult` — one per URL across all specs.
        """
        results: list[BatchResult] = []
        row = 0
        for spec in specs:
            targets: list[str] = spec.pop("targets", [])
            if not targets:
                continue
            for url in targets:
                row += 1
                try:
                    files = self.download(url, **spec)
                    results.append(BatchResult(
                        row=row,
                        url=url,
                        success=len(files) > 0,
                        files=files,
                    ))
                except Exception as exc:  # noqa: BLE001
                    results.append(BatchResult(
                        row=row,
                        url=url,
                        success=False,
                        error=str(exc),
                    ))

        return results


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
    "BatchResult",
    "get_youtube_service",
    "build_format_selector",
    "build_subtitle_opts",
    "parse_csv_rows",
]
