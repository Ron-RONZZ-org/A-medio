"""Tests for A_medio.services.youtube — yt-dlp wrapper service layer."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from A_medio.services.youtube import (
    YouTubeService,
    YouTubeVideo,
    YtDlpWrapper,
    build_format_selector,
    build_subtitle_opts,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Format selector
# ═══════════════════════════════════════════════════════════════════════════════


class TestBuildFormatSelector:
    """build_format_selector returns correct yt-dlp format strings."""

    def test_default_best(self) -> None:
        """Default (no args) returns ``'best'``."""
        assert build_format_selector() == "best"

    def test_resolution(self) -> None:
        """With resolution, returns ``'best[height<=N]/best'``."""
        assert build_format_selector(resolution=720) == "best[height<=720]/best"
        assert build_format_selector(resolution=1080) == "best[height<=1080]/best"

    def test_audio_only(self) -> None:
        """Audio-only returns ``'bestaudio'``."""
        assert build_format_selector(audio_only=True) == "bestaudio"

    def test_audio_only_with_bitrate(self) -> None:
        """Audio-only with bitrate returns ``'bestaudio[abr<=N]/bestaudio'``."""
        result = build_format_selector(audio_only=True, audio_bitrate=128)
        assert result == "bestaudio[abr<=128]/bestaudio"

    def test_video_only(self) -> None:
        """Video-only returns ``'bestvideo'``."""
        assert build_format_selector(video_only=True) == "bestvideo"

    def test_video_only_with_resolution(self) -> None:
        """Video-only with resolution returns ``'bestvideo[height<=N]/bestvideo'``."""
        result = build_format_selector(video_only=True, resolution=720)
        assert result == "bestvideo[height<=720]/bestvideo"

    def test_audio_and_video_raises(self) -> None:
        """Using both ``audio_only`` and ``video_only`` raises ValueError."""
        with pytest.raises(ValueError, match="Cannot use both"):
            build_format_selector(audio_only=True, video_only=True)


# ═══════════════════════════════════════════════════════════════════════════════
# Subtitle options
# ═══════════════════════════════════════════════════════════════════════════════


class TestBuildSubtitleOpts:
    """build_subtitle_opts returns correct yt-dlp subtitle options."""

    def test_no_subtitles(self) -> None:
        """None returns empty dict."""
        assert build_subtitle_opts(None) == {}

    def test_empty_string(self) -> None:
        """Empty string returns empty dict."""
        assert build_subtitle_opts("") == {}

    def test_auto(self) -> None:
        """``'auto'`` enables automatic subtitles."""
        opts = build_subtitle_opts("auto")
        assert opts["writesubtitles"] is True
        assert opts["writeautomaticsub"] is True
        assert opts["subtitlesformat"] == "best"

    def test_all(self) -> None:
        """``'all'`` enables automatic subtitles."""
        opts = build_subtitle_opts("all")
        assert opts["writesubtitles"] is True
        assert opts["writeautomaticsub"] is True

    def test_language_codes(self) -> None:
        """Comma-separated language codes produce ``subtitleslangs`` list."""
        opts = build_subtitle_opts("eo,en,fr")
        assert opts["writesubtitles"] is True
        assert opts["writeautomaticsub"] is False
        assert opts["subtitleslangs"] == ["eo", "en", "fr"]

    def test_single_language(self) -> None:
        """Single language code."""
        opts = build_subtitle_opts("en")
        assert opts["subtitleslangs"] == ["en"]

    def test_whitespace_handling(self) -> None:
        """Whitespace around language codes is stripped."""
        opts = build_subtitle_opts(" eo , en ")
        assert opts["subtitleslangs"] == ["eo", "en"]


# ═══════════════════════════════════════════════════════════════════════════════
# YtDlpWrapper
# ═══════════════════════════════════════════════════════════════════════════════


class TestYtDlpWrapper:
    """YtDlpWrapper singleton and availability detection."""

    def test_singleton(self) -> None:
        """Multiple instantiations return the same object."""
        a = YtDlpWrapper()
        b = YtDlpWrapper()
        assert a is b

    @patch("shutil.which", return_value=None)
    def test_not_available_without_yt_dlp(self, mock_which: MagicMock) -> None:
        """Returns False when neither binary nor library is found."""
        wrapper = YtDlpWrapper()
        wrapper._available = None  # Reset cache for test

        with patch.dict("sys.modules", {"yt_dlp": None}):
            # Force import to fail
            import builtins

            original_import = builtins.__import__

            def fake_import(name, *args, **kwargs):
                if name == "yt_dlp":
                    raise ImportError
                return original_import(name, *args, **kwargs)

            with patch.object(builtins, "__import__", fake_import):
                assert wrapper.is_available() is False

    @patch("shutil.which", return_value="/usr/bin/yt-dlp")
    def test_available_with_binary(self, mock_which: MagicMock) -> None:
        """Returns True when yt-dlp binary is found."""
        wrapper = YtDlpWrapper()
        wrapper._available = None
        assert wrapper.is_available() is True

    @patch("shutil.which", return_value=None)
    def test_create_ydl_raises_when_unavailable(self, mock_which: MagicMock) -> None:
        """``create_ydl()`` raises RuntimeError when yt-dlp is unavailable."""
        wrapper = YtDlpWrapper()
        wrapper._available = None

        import builtins

        original_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "yt_dlp":
                raise ImportError
            return original_import(name, *args, **kwargs)

        with patch.object(builtins, "__import__", fake_import):
            with pytest.raises(RuntimeError, match="not available"):
                with wrapper.create_ydl():
                    pass


# ═══════════════════════════════════════════════════════════════════════════════
# YouTubeVideo
# ═══════════════════════════════════════════════════════════════════════════════


class TestYouTubeVideo:
    """YouTubeVideo data object."""

    def test_from_yt_dlp_minimal(self) -> None:
        """from_yt_dlp handles minimal data with defaults."""
        video = YouTubeVideo.from_yt_dlp({"id": "abc123", "title": "Test"})
        assert video.video_id == "abc123"
        assert video.title == "Test"
        assert video.description == ""
        assert video.duration == 0
        assert video.url == "https://www.youtube.com/watch?v=abc123"

    def test_from_yt_dlp_full(self) -> None:
        """from_yt_dlp extracts all fields."""
        data = {
            "id": "xyz789",
            "title": "Full Video",
            "description": "A description",
            "uploader": "Channel Name",
            "duration": 300,
            "view_count": 1000,
            "upload_date": "20240101",
            "thumbnail": "https://img.youtube.com/vi/xyz789/hqdefault.jpg",
            "webpage_url": "https://youtu.be/xyz789",
        }
        video = YouTubeVideo.from_yt_dlp(data)
        assert video.video_id == "xyz789"
        assert video.title == "Full Video"
        assert video.description == "A description"
        assert video.author == "Channel Name"
        assert video.duration == 300
        assert video.view_count == 1000
        assert video.upload_date == "20240101"
        assert video.url == "https://youtu.be/xyz789"

    def test_to_dict(self) -> None:
        """to_dict returns correct keys."""
        video = YouTubeVideo(video_id="abc", title="T")
        d = video.to_dict()
        assert d["video_id"] == "abc"
        assert d["title"] == "T"
        assert "url" in d


# ═══════════════════════════════════════════════════════════════════════════════
# YouTubeService
# ═══════════════════════════════════════════════════════════════════════════════


class TestYouTubeService:
    """YouTubeService — download method and availability."""

    def test_is_available_delegates_to_wrapper(self) -> None:
        """is_available() checks the YtDlpWrapper."""
        service = YouTubeService()
        with patch.object(service._wrapper, "is_available", return_value=True):
            assert service.is_available() is True

    def test_get_download_dir(self) -> None:
        """get_download_dir returns a string."""
        service = YouTubeService()
        with patch("A_medio.services.youtube.get_download_dir", return_value="/tmp/medio"):
            result = service.get_download_dir()
            assert result == "/tmp/medio"

    def test_download_returns_empty_when_unavailable(self) -> None:
        """download() returns [] when yt-dlp is not available."""
        service = YouTubeService()
        with patch.object(service, "is_available", return_value=False):
            result = service.download("https://youtu.be/abc")
            assert result == []

    def test_download_creates_output_dir(self, tmp_path: Path) -> None:
        """download() creates the output directory."""
        service = YouTubeService()
        dl_dir = str(tmp_path / "downloads")
        with (
            patch.object(service, "is_available", return_value=True),
            patch("A_medio.services.youtube.get_download_dir", return_value=dl_dir),
            patch.object(service._wrapper, "create_ydl") as mock_create,
        ):
            mock_ydl = MagicMock()
            mock_create.return_value.__enter__.return_value = mock_ydl

            service.download("https://youtu.be/abc")

            # Directory should have been created
            assert Path(dl_dir).exists()

    def test_download_with_all_options(self, tmp_path: Path) -> None:
        """download() passes correct options to yt-dlp."""
        service = YouTubeService()
        dl_dir = str(tmp_path / "custom")
        with (
            patch.object(service, "is_available", return_value=True),
            patch("A_medio.services.youtube.get_download_dir", return_value=str(tmp_path)),
            patch.object(service._wrapper, "create_ydl") as mock_create,
        ):
            mock_ydl = MagicMock()
            mock_create.return_value.__enter__.return_value = mock_ydl

            service.download(
                "https://youtu.be/abc",
                output_dir=dl_dir,
                resolution=720,
                audio_only=False,
                video_only=True,
                audio_bitrate=128,
                subtitles="eo,en",
            )

            call_kwargs = mock_create.call_args[0][0]
            assert dl_dir in call_kwargs["outtmpl"]
            assert "bestvideo[height<=720]/bestvideo" in call_kwargs["format"]
            assert call_kwargs["writesubtitles"] is True
            assert call_kwargs["subtitleslangs"] == ["eo", "en"]


# ═══════════════════════════════════════════════════════════════════════════════
# CLI integration
# ═══════════════════════════════════════════════════════════════════════════════


class TestFilmetoEljutiCLI:
    """``medio filmeto eljuti`` CLI command."""

    def test_eljuti_requires_url(self) -> None:
        """Running eljuti without URL should fail."""
        from typer.testing import CliRunner

        from A_medio.cli import app

        runner = CliRunner()
        result = runner.invoke(app, ["filmeto", "eljuti"])
        assert result.exit_code != 0

    def test_eljuti_with_url(self) -> None:
        """Running eljuti with URL invokes download."""
        from typer.testing import CliRunner

        from A_medio.cli import app

        runner = CliRunner()

        with patch("A_medio.cli.get_youtube_service") as mock_get:
            mock_service = MagicMock()
            # Make yt-dlp available
            mock_service.is_available.return_value = True
            # Return an empty list for the download
            mock_service.download.return_value = []
            mock_get.return_value = mock_service

            result = runner.invoke(app, [
                "filmeto", "eljuti",
                "https://youtu.be/abc123",
            ])

            assert result.exit_code == 0
            mock_service.download.assert_called_once_with(
                "https://youtu.be/abc123",
                output_dir=mock_service.get_download_dir(),
            )

    def test_eljuti_with_options(self) -> None:
        """CLI passes download options correctly."""
        from typer.testing import CliRunner

        from A_medio.cli import app

        runner = CliRunner()

        with patch("A_medio.cli.get_youtube_service") as mock_get:
            mock_service = MagicMock()
            mock_service.is_available.return_value = True
            mock_service.get_download_dir.return_value = "/tmp/medio"
            mock_service.download.return_value = [Path("/tmp/video.mp4")]
            mock_get.return_value = mock_service

            result = runner.invoke(app, [
                "filmeto", "eljuti",
                "https://youtu.be/abc123",
                "--difino", "1080",
                "--audio",
                "--subtitoloj", "eo,en",
            ])

            assert result.exit_code == 0
            mock_service.download.assert_called_once_with(
                "https://youtu.be/abc123",
                output_dir="/tmp/medio",
                resolution=1080,
                audio_only=True,
                subtitles="eo,en",
            )

    def test_eljuti_reports_unavailable(self) -> None:
        """Running eljuti when yt-dlp unavailable shows error."""
        from typer.testing import CliRunner

        from A_medio.cli import app

        runner = CliRunner()

        with patch("A_medio.cli.get_youtube_service") as mock_get:
            mock_service = MagicMock()
            mock_service.is_available.return_value = False
            mock_get.return_value = mock_service

            result = runner.invoke(app, [
                "filmeto", "eljuti",
                "https://youtu.be/abc123",
            ])

            assert "ne estas instalita" in result.stdout or "not installed" in result.stdout
            assert not mock_service.download.called
