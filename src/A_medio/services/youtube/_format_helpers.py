"""Format selector and subtitle option builders for yt-dlp."""

from __future__ import annotations

from typing import Any


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
