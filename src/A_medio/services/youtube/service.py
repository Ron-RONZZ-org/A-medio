"""YouTubeService — search, download, and estimate YouTube videos."""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    TextColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)

from A import error, info, tr_multi
from A.core.service import CRUDService
from A.data.search import FTSConfig
from A.utils.normalize import fold_search_text

from A_medio.config import (
    get_cookies_from_browser,
    get_cookies_from_browser_profile,
    get_download_dir,
)
from A_medio.services.base import MediaService
from A_medio.services.youtube._wrapper import YtDlpWrapper, get_download_error
from A_medio.services.youtube._models import YouTubeVideo, BatchResult, EstimateResult
from A_medio.services.youtube._format_helpers import build_format_selector, build_subtitle_opts
from A_medio.services.youtube._cookie_helpers import _cookie_browser_candidates
from A_medio.services.youtube._strategy import _load_search_strategy, _save_search_strategy
from A_medio.services.youtube._csv_helpers import parse_csv_rows
from A_medio.data.storage import get_db


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

    def ensure_installed(self) -> bool:
        """Ensure yt-dlp is installed, prompting the user if missing."""
        return self._wrapper.ensure_installed()

    def get_download_dir(self) -> str:
        """Return the configured download directory."""
        return get_download_dir()

    # ── shared helpers ────────────────────────────────────────────────────

    def _build_cookie_candidates(
        self,
        base_opts: dict[str, Any],
        *,
        cookies: str | None = None,
        cookies_from_browser: str | None = None,
    ) -> list[dict[str, Any]]:
        """Build yt-dlp opts variants with different cookie sources.

        Returns candidates in priority order:
        1. Explicit ``--kuketoj`` file (if provided)
        2. Browser cookies (explicit flag or config fallback)
        3. Bare fallback (no cookies)

        Each candidate is a *copy* of ``base_opts`` with cookie options added.
        """
        candidates: list[dict[str, Any]] = []

        # 1. Explicit --kuketoj file
        if cookies:
            with_cookie = dict(base_opts)
            with_cookie["cookiefile"] = cookies
            candidates.append(with_cookie)

        # 2. Browser cookies (explicit or config fallback)
        effective_browser = cookies_from_browser or get_cookies_from_browser()
        effective_profile = (
            get_cookies_from_browser_profile()
            if not cookies_from_browser else None
        )

        for browser_spec in _cookie_browser_candidates(
            cookies_from_browser,
            config_browser=effective_browser,
            config_profile=effective_profile,
        ):
            with_browser = dict(base_opts)
            if browser_spec is not None:
                with_browser["cookiesfrombrowser"] = browser_spec
            candidates.append(with_browser)

        # 3. Bare fallback (no cookies) — ensure it appears at least once
        bare = dict(base_opts)
        if bare not in candidates:
            candidates.append(bare)

        return candidates

    # ── search ────────────────────────────────────────────────────────────

    def _yt_dlp_search(
        self,
        query: str,
        limit: int = 10,
        cookies: str | None = None,
        cookies_from_browser: str | None = None,
    ) -> list[YouTubeVideo]:
        """Search YouTube via yt-dlp with retry strategy."""
        if not self.is_available():
            error(tr_multi(
                "yt-dlp ne estas instalita. Instalu ĝin por uzi serĉon.",
                "yt-dlp is not installed. Install it to use search.",
                "yt-dlp n'est pas installe. Installez-le pour utiliser la recherche.",
            ))
            return []

        base_opts: dict[str, Any] = {
            "quiet": True,
            "skip_download": True,
            "no_warnings": True,
            "ignoreerrors": True,
            "extract_flat": False,
        }

        candidates: list[dict[str, Any]] = []

        cached = _load_search_strategy()
        cached_opts = cached.get("opts")
        if isinstance(cached_opts, dict):
            candidates.append(dict(cached_opts))

        if cookies:
            with_cookie = dict(base_opts)
            with_cookie["cookiefile"] = cookies
            candidates.append(with_cookie)

        # When no explicit --kuketoj-de-retumilo flag, fall back to config
        effective_browser = cookies_from_browser or get_cookies_from_browser()
        effective_profile = get_cookies_from_browser_profile() if not cookies_from_browser else None

        for browser_spec in _cookie_browser_candidates(
            cookies_from_browser,
            config_browser=effective_browser,
            config_profile=effective_profile,
        ):
            with_browser = dict(base_opts)
            if browser_spec is not None:
                with_browser["cookiesfrombrowser"] = browser_spec
            candidates.append(with_browser)

        if not candidates:
            candidates.append(dict(base_opts))

        search_query = f"ytsearch{max(1, limit)}:{query}"
        last_error: Exception | None = None
        pending = list(candidates)
        seen: set[str] = set()

        while pending:
            opts = pending.pop(0)
            opts_key = json.dumps(opts, sort_keys=True, default=str)
            if opts_key in seen:
                continue
            seen.add(opts_key)

            try:
                with self._wrapper.create_ydl(opts) as ydl:
                    result = ydl.extract_info(search_query, download=False)
            except get_download_error() as exc:
                last_error = exc
                msg = str(exc).lower()
                if ("certificate_verify_failed" in msg or "hostname mismatch" in msg
                        or "certificateverifyerror" in msg) and not opts.get("nocheckcertificate"):
                    retry = dict(opts)
                    retry["nocheckcertificate"] = True
                    pending.append(retry)
                if "requested format is not available" in msg and not opts.get("extract_flat"):
                    retry = dict(opts)
                    retry["extract_flat"] = True
                    pending.append(retry)
                continue

            entries = result.get("entries") if isinstance(result, dict) else []
            filtered = [
                e for e in list(entries or [])
                if isinstance(e, dict)
                and str(e.get("availability") or "").lower() not in {
                    "private", "premium_only", "subscriber_only",
                    "needs_auth", "unavailable",
                }
            ]

            if filtered:
                _save_search_strategy({"opts": opts, "source": "search-success"})
                return [YouTubeVideo.from_yt_dlp(e) for e in filtered]

            if not opts.get("nocheckcertificate"):
                retry = dict(opts)
                retry["nocheckcertificate"] = True
                pending.append(retry)
            if not opts.get("extract_flat"):
                retry = dict(opts)
                retry["extract_flat"] = True
                pending.append(retry)

        if last_error:
            error(tr_multi(
                f"Serĉo fiaskis: {last_error}",
                f"Search failed: {last_error}",
                f"Echec de recherche: {last_error}",
            ))
        else:
            error(tr_multi(
                "Neniuj rezultoj trovitaj.",
                "No results found.",
                "Aucun resultat trouve.",
            ))
        return []

    def search(
        self,
        query: str,
        **opts: Any,
    ) -> list[dict[str, Any]]:
        """Search YouTube for videos."""
        limit = opts.get("limit", 10)
        cookies = opts.get("cookies")
        cookies_from_browser = opts.get("cookies_from_browser")

        videos = self._yt_dlp_search(
            query,
            limit=limit,
            cookies=cookies,
            cookies_from_browser=cookies_from_browser,
        )

        if not videos:
            return []

        service = self.get_service()
        now = datetime.now().isoformat()
        for video in videos:
            existing = service.get_by_field("video_id", video.video_id)
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

    def get_by_id(self, video_id: str) -> dict[str, Any] | None:
        """Get a video by ID from local cache.

        Args:
            video_id: The YouTube video ID.

        Returns:
            Video dict or ``None``.
        """
        service = self.get_service()
        return service.get_by_field("video_id", video_id)

    def search_local(
        self,
        query: str,
        **opts: Any,
    ) -> list[dict[str, Any]]:
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
                - outtmpl: yt-dlp output template override (default:
                  ``"%(title).80s [%(id)s].%(ext)s"``).
                - resolution: Max video height (e.g. 720, 1080).
                - audio_only: Extract audio only.
                - video_only: Video stream only (no audio).
                - audio_bitrate: Max audio bitrate in kbps.
                - subtitles: Subtitle spec (auto, all, or langs).
                - cookies: Path to cookies.txt file.
                - cookies_from_browser: Browser name or ``"browser:profile"``.
                - playlist_end: Max number of items from a playlist.

        Returns:
            List of paths to downloaded files (empty if failed).
        """
        if not self.is_available():
            error(tr_multi(
                "yt-dlp ne estas instalita. Instalu ĝin por elŝuti.",
                "yt-dlp is not installed. Install it to download.",
                "yt-dlp n'est pas installe. Installez-le pour telecharger.",
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

        default_template = "%(title).80s [%(id)s].%(ext)s"
        outtmpl = opts.get("outtmpl", default_template)

        base_ydl_opts: dict[str, Any] = {
            "quiet": True,
            "no_warnings": True,
            "format": format_sel,
            "outtmpl": str(output_dir / outtmpl),
            "ignoreerrors": True,
        }
        if opts.get("playlist_end") is not None:
            base_ydl_opts["playlistend"] = int(opts["playlist_end"])
        base_ydl_opts.update(build_subtitle_opts(opts.get("subtitles")))

        # ── Rich progress bar (interactive terminals only) ──────────────
        progress: Progress | None = None
        _task_id: int | None = None

        if sys.stdout.isatty():
            progress = Progress(
                TextColumn("{task.description}"),
                BarColumn(),
                TextColumn("{task.percentage:>3.0f}%"),
                DownloadColumn(),
                TransferSpeedColumn(),
                TimeRemainingColumn(),
                transient=True,
            )
            progress.start()
            _task_id = progress.add_task("Elŝutado", total=None)

            def _yt_progress_hook(d: dict) -> None:
                if d["status"] == "downloading":
                    total = d.get("total_bytes") or d.get("total_bytes_estimate")
                    if total:
                        progress.update(_task_id, total=int(total))
                        progress.update(_task_id, completed=d.get("downloaded_bytes", 0))
                    filename = d.get("filename", "")
                    if filename:
                        progress.update(_task_id, description=Path(filename).name)
                elif d["status"] == "finished":
                    total = d.get("total_bytes") or 0
                    progress.update(_task_id, completed=int(total), total=int(total or 1))

            base_ydl_opts["progress_hooks"] = [_yt_progress_hook]

        candidates = self._build_cookie_candidates(
            base_ydl_opts,
            cookies=opts.get("cookies"),
            cookies_from_browser=opts.get("cookies_from_browser"),
        )

        before = {p for p in output_dir.iterdir()} if output_dir.exists() else set()
        last_error: Exception | None = None

        try:
            for ydl_opts in candidates:
                try:
                    with self._wrapper.create_ydl(ydl_opts) as ydl:
                        ydl.extract_info(url, download=True)

                    # Check if anything was actually created
                    after = {p for p in output_dir.iterdir()}
                    if after - before:
                        break  # success
                except get_download_error() as exc:
                    last_error = exc
        finally:
            if progress:
                progress.stop()

        after = {p for p in output_dir.iterdir()}
        created = sorted(after - before, key=lambda p: p.name)

        if not created and last_error:
            error(tr_multi(
                f"Elŝuto fiaskis: {last_error}",
                f"Download failed: {last_error}",
                f"Telechargement echoue: {last_error}",
            ))

        if created:
            info(tr_multi(
                f"Elŝutis {len(created)} dosiero(j)n al {output_dir}",
                f"Downloaded {len(created)} file(s) to {output_dir}",
                f"Telecharge {len(created)} fichier(s) vers {output_dir}",
            ))
        else:
            info(tr_multi(
                "Neniu dosiero elŝutita.",
                "No files downloaded.",
                "Aucun fichier telecharge.",
            ))

        return created

    # ── estimate ─────────────────────────────────────────────────────────

    def estimate(
        self,
        url: str,
        **opts: Any,
    ) -> EstimateResult | None:
        """Estimate download size without downloading.

        Runs a dry-run ``extract_info`` with the same format options as
        :meth:`download` and sums up file sizes.

        Args:
            url: YouTube URL to estimate.
            **opts: Same options as :meth:`download` (format, cookies, etc.).

        Returns:
            :class:`EstimateResult`, or ``None`` if estimation fails.
        """
        if not self.is_available():
            error(tr_multi(
                "yt-dlp ne estas instalita.",
                "yt-dlp is not installed.",
                "yt-dlp n'est pas installe.",
            ))
            return None

        format_sel = build_format_selector(
            resolution=opts.get("resolution"),
            audio_only=opts.get("audio_only", False),
            video_only=opts.get("video_only", False),
            audio_bitrate=opts.get("audio_bitrate"),
        )

        base_ydl_opts: dict[str, Any] = {
            "quiet": True,
            "no_warnings": True,
            "format": format_sel,
            "skip_download": True,
            "ignoreerrors": True,
        }
        if opts.get("playlist_end") is not None:
            base_ydl_opts["playlistend"] = int(opts["playlist_end"])

        candidates = self._build_cookie_candidates(
            base_ydl_opts,
            cookies=opts.get("cookies"),
            cookies_from_browser=opts.get("cookies_from_browser"),
        )

        last_error: Exception | None = None
        info_data: dict[str, Any] | None = None

        for ydl_opts in candidates:
            try:
                with self._wrapper.create_ydl(ydl_opts) as ydl:
                    raw = ydl.extract_info(url, download=False)
            except get_download_error() as exc:
                last_error = exc
                continue

            # ignoreerrors=True can return None; try next candidate
            if raw is None:
                continue

            # Unwrap single-entry playlist that yt-dlp sometimes wraps
            if isinstance(raw, dict):
                entries = raw.get("entries")
                if isinstance(entries, list) and len(entries) == 1 and entries[0] is not None:
                    raw = entries[0]

            info_data = raw
            break

        if info_data is None:
            if last_error:
                error(tr_multi(
                    f"Takso fiaskis: {last_error}",
                    f"Estimation failed: {last_error}",
                    f"Estimation echouee: {last_error}",
                ))
            return None

        items_list: list[dict[str, Any]] = []
        entries = info_data.get("entries") if isinstance(info_data, dict) else None
        if entries:
            for entry in entries:
                if isinstance(entry, dict):
                    items_list.append(entry)
        elif isinstance(info_data, dict):
            items_list.append(info_data)

        total = 0
        item_details: list[dict[str, Any]] = []
        for item in items_list:
            filesize = (
                item.get("filesize")
                or item.get("filesize_approx")
                or 0
            )
            if isinstance(filesize, (int, float)):
                total += int(filesize)
            item_details.append({
                "title": item.get("title", ""),
                "duration": item.get("duration", 0),
                "filesize": int(filesize) if filesize else 0,
                "url": item.get("webpage_url") or item.get("url", ""),
            })

        return EstimateResult(
            count=len(item_details),
            total_bytes=total,
            items=item_details,
        )

    # ── batch download ───────────────────────────────────────────────────

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


# ── Service singleton ──────────────────────────────────────────────────────

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
