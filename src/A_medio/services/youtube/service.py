"""YouTubeService — search, download, and estimate YouTube videos."""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from A import error, info, tr_multi
from A.core.service import CRUDService
from A.data.search import FTSConfig
from A.utils.normalize import fold_search_text

from A_medio.config import get_download_dir
from A_medio.services.base import MediaService
from A_medio.services.youtube._wrapper import YtDlpWrapper, get_download_error
from A_medio.services.youtube._models import YouTubeVideo, BatchResult, EstimateResult
from A_medio.services.youtube._format_helpers import build_format_selector, build_subtitle_opts
from A_medio.services.youtube._cookie_helpers import build_cookie_opts, _cookie_browser_candidates
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
                "yt-dlp ne estas instalita. Instalu ghin por uzi sercon.",
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

        for browser_spec in _cookie_browser_candidates(cookies_from_browser):
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
                f"Sercxo fiaskis: {last_error}",
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


# ── batch download ───────────────────────────────────────────────────

    def batch_download(
        self,
        specs: list[dict[str, Any]],
    ) -> list[BatchResult]:
        """Download multiple items from a list of download specs."""
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
