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
    parse_csv_rows,
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

    def test_eljuti_requires_url_or_csv(self) -> None:
        """Running eljuti without URL and without --csv-dosiero shows error."""
        from typer.testing import CliRunner

        from A_medio.cli import app

        runner = CliRunner()

        with patch("A_medio.cli.get_youtube_service") as mock_get:
            mock_service = MagicMock()
            mock_service.is_available.return_value = True
            mock_get.return_value = mock_service

            result = runner.invoke(app, ["filmeto", "eljuti"])

            assert result.exit_code == 0
            assert "Mankas URL" in result.stdout or "Missing URL" in result.stdout

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


# ═══════════════════════════════════════════════════════════════════════════════
# CSV parsing
# ═══════════════════════════════════════════════════════════════════════════════


class TestParseCsvRows:
    """parse_csv_rows — CSV batch download parsing."""

    def test_missing_file(self) -> None:
        """Non-existent CSV raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError, match="ne trovita"):
            parse_csv_rows("/tmp/nonexistent_csv_test_file_xyz.csv")

    def test_minimal_csv(self, tmp_path: Path) -> None:
        """CSV with only celoj column works."""
        csv_file = tmp_path / "batch.csv"
        csv_file.write_text("celoj\nhttps://youtu.be/abc\n")

        rows = parse_csv_rows(csv_file)
        assert len(rows) == 1
        assert rows[0]["targets"] == ["https://youtu.be/abc"]
        assert rows[0]["resolution"] is None

    def test_multiple_rows(self, tmp_path: Path) -> None:
        """Multiple CSV rows produce multiple specs."""
        csv_file = tmp_path / "multi.csv"
        csv_file.write_text(
            "celoj,difino\n"
            "https://youtu.be/a,720\n"
            "https://youtu.be/b,1080\n"
        )

        rows = parse_csv_rows(csv_file)
        assert len(rows) == 2
        assert rows[0]["targets"] == ["https://youtu.be/a"]
        assert rows[0]["resolution"] == 720
        assert rows[1]["targets"] == ["https://youtu.be/b"]
        assert rows[1]["resolution"] == 1080

    def test_bool_columns(self, tmp_path: Path) -> None:
        """Bool columns (audio, filmeto) are parsed correctly."""
        csv_file = tmp_path / "bool.csv"
        csv_file.write_text(
            "celoj,audio,filmeto\n"
            "https://youtu.be/a,true,false\n"
            "https://youtu.be/b,false,true\n"
            "https://youtu.be/c,1,0\n"
        )

        rows = parse_csv_rows(csv_file)
        assert rows[0]["audio_only"] is True
        assert rows[0]["video_only"] is False
        assert rows[1]["audio_only"] is False
        assert rows[1]["video_only"] is True
        assert rows[2]["audio_only"] is True
        assert rows[2]["video_only"] is False

    def test_state_inheritance(self, tmp_path: Path) -> None:
        """Empty cells inherit from previous row or initial_state."""
        csv_file = tmp_path / "inherit.csv"
        csv_file.write_text(
            "celoj,difino\n"
            "https://youtu.be/a,720\n"
            "https://youtu.be/b,\n"  # inherits 720
        )

        rows = parse_csv_rows(csv_file, initial_state={"resolution": 480})
        assert rows[0]["resolution"] == 720  # explicit
        assert rows[1]["resolution"] == 720  # inherited from row 1

    def test_initial_state(self, tmp_path: Path) -> None:
        """initial_state provides defaults for first row."""
        csv_file = tmp_path / "init.csv"
        csv_file.write_text("celoj\nhttps://youtu.be/a\n")

        rows = parse_csv_rows(csv_file, initial_state={"output_dir": "/videos"})
        assert rows[0]["output_dir"] == "/videos"

    def test_esperanto_headers(self, tmp_path: Path) -> None:
        """Esperanto column headers are recognized."""
        csv_file = tmp_path / "eo.csv"
        csv_file.write_text(
            "celoj,difino,sonkvalito,audio,filmeto,vojo,subtitoloj\n"
            "https://youtu.be/a,720,128,true,false,/output,\"eo,en\"\n"
        )

        rows = parse_csv_rows(csv_file)
        assert rows[0]["targets"] == ["https://youtu.be/a"]
        assert rows[0]["resolution"] == 720
        assert rows[0]["audio_bitrate"] == 128
        assert rows[0]["audio_only"] is True
        assert rows[0]["video_only"] is False
        assert rows[0]["output_dir"] == "/output"
        assert rows[0]["subtitles"] == "eo,en"

    def test_missing_celoj_column(self, tmp_path: Path) -> None:
        """CSV without celoj column raises ValueError."""
        csv_file = tmp_path / "bad.csv"
        csv_file.write_text("titolo\nvideo\n")

        with pytest.raises(ValueError, match="celoj"):
            parse_csv_rows(csv_file)

    def test_empty_csv(self, tmp_path: Path) -> None:
        """CSV with no headers raises ValueError."""
        csv_file = tmp_path / "empty.csv"
        csv_file.write_text("")

        with pytest.raises(ValueError, match="malplena"):
            parse_csv_rows(csv_file)

    def test_invalid_bool(self, tmp_path: Path) -> None:
        """Invalid boolean value raises ValueError."""
        csv_file = tmp_path / "badbool.csv"
        csv_file.write_text("celoj,audio\nhttps://youtu.be/a,maybe\n")

        with pytest.raises(ValueError, match="nevalida valoro"):
            parse_csv_rows(csv_file)

    def test_invalid_int(self, tmp_path: Path) -> None:
        """Invalid integer value raises ValueError."""
        csv_file = tmp_path / "badint.csv"
        csv_file.write_text("celoj,difino\nhttps://youtu.be/a,notanumber\n")

        with pytest.raises(ValueError, match="nevalida nombro"):
            parse_csv_rows(csv_file)

    def test_multiple_targets_in_cell(self, tmp_path: Path) -> None:
        """Multiple URLs in one celoj cell are split."""
        csv_file = tmp_path / "multiurl.csv"
        csv_file.write_text("celoj\nhttps://youtu.be/a https://youtu.be/b\n")

        rows = parse_csv_rows(csv_file)
        assert len(rows) == 1
        assert rows[0]["targets"] == ["https://youtu.be/a", "https://youtu.be/b"]

    def test_english_headers(self, tmp_path: Path) -> None:
        """English column headers are recognized."""
        csv_file = tmp_path / "en.csv"
        csv_file.write_text(
            "targets,resolution,subtitles\n"
            "https://youtu.be/a,720,en\n"
        )

        rows = parse_csv_rows(csv_file)
        assert rows[0]["targets"] == ["https://youtu.be/a"]
        assert rows[0]["resolution"] == 720
        assert rows[0]["subtitles"] == "en"


# ═══════════════════════════════════════════════════════════════════════════════
# Batch download
# ═══════════════════════════════════════════════════════════════════════════════


class TestBatchDownload:
    """batch_download processes multiple specs."""

    def test_batch_empty(self) -> None:
        """Empty spec list returns empty results."""
        service = YouTubeService()
        results = service.batch_download([])
        assert results == []

    def test_batch_single_spec(self) -> None:
        """Single spec with one URL calls download once."""
        service = YouTubeService()
        with patch.object(service, "download", return_value=[Path("/v/a.mp4")]) as mock_dl:
            results = service.batch_download([
                {"targets": ["https://youtu.be/a"], "resolution": 720},
            ])

        assert len(results) == 1
        assert results[0].success is True
        assert results[0].url == "https://youtu.be/a"
        assert results[0].files == [Path("/v/a.mp4")]
        mock_dl.assert_called_once_with("https://youtu.be/a", resolution=720)

    def test_batch_multiple_specs(self) -> None:
        """Multiple specs each call download."""
        service = YouTubeService()
        with patch.object(service, "download", return_value=[Path("/v/a.mp4")]) as mock_dl:
            results = service.batch_download([
                {"targets": ["https://youtu.be/a"]},
                {"targets": ["https://youtu.be/b", "https://youtu.be/c"]},
            ])

        assert len(results) == 3
        assert mock_dl.call_count == 3

    def test_batch_handles_download_failure(self) -> None:
        """When download returns [], result is failure."""
        service = YouTubeService()
        with patch.object(service, "download", return_value=[]):
            results = service.batch_download([
                {"targets": ["https://youtu.be/a"]},
            ])

        assert len(results) == 1
        assert results[0].success is False

    def test_batch_handles_exception(self) -> None:
        """Exception in download is caught and reported."""
        service = YouTubeService()
        with patch.object(service, "download", side_effect=RuntimeError("oops")):
            results = service.batch_download([
                {"targets": ["https://youtu.be/a"]},
            ])

        assert len(results) == 1
        assert results[0].success is False
        assert "oops" in results[0].error


# ═══════════════════════════════════════════════════════════════════════════════
# CLI CSV integration
# ═══════════════════════════════════════════════════════════════════════════════


class TestFilmetoEljutiCSV:
    """``medio filmeto eljuti --csv-dosiero`` CLI command."""

    def test_csv_flag_accepted(self, tmp_path: Path) -> None:
        """CLI accepts --csv-dosiero flag."""
        csv_file = tmp_path / "batch.csv"
        csv_file.write_text("celoj\nhttps://youtu.be/abc\n")

        from typer.testing import CliRunner

        from A_medio.cli import app

        runner = CliRunner()

        with patch("A_medio.cli.get_youtube_service") as mock_get:
            mock_service = MagicMock()
            mock_service.is_available.return_value = True
            mock_service.batch_download.return_value = []
            mock_get.return_value = mock_service

            result = runner.invoke(app, [
                "filmeto", "eljuti",
                "--csv-dosiero", str(csv_file),
            ])

            assert result.exit_code == 0
            mock_service.batch_download.assert_called_once()

    def test_csv_with_cli_flags(self, tmp_path: Path) -> None:
        """CLI flags are passed as initial_state to parse_csv_rows."""
        csv_file = tmp_path / "batch2.csv"
        csv_file.write_text("celoj\nhttps://youtu.be/abc\n")

        from typer.testing import CliRunner

        from A_medio.cli import app

        runner = CliRunner()

        with patch("A_medio.cli.get_youtube_service") as mock_get:
            mock_service = MagicMock()
            mock_service.is_available.return_value = True
            mock_service.batch_download.return_value = []
            mock_get.return_value = mock_service

            result = runner.invoke(app, [
                "filmeto", "eljuti",
                "--csv-dosiero", str(csv_file),
                "--difino", "720",
                "--audio",
            ])

            assert result.exit_code == 0
            # batch_download was called (specs parsed from CSV + initial state)
            mock_service.batch_download.assert_called_once()

    def test_csv_file_not_found(self, tmp_path: Path) -> None:
        """Non-existent CSV file shows error."""
        from typer.testing import CliRunner

        from A_medio.cli import app

        runner = CliRunner()

        with patch("A_medio.cli.get_youtube_service") as mock_get:
            mock_service = MagicMock()
            mock_service.is_available.return_value = True
            mock_get.return_value = mock_service

            result = runner.invoke(app, [
                "filmeto", "eljuti",
                "--csv-dosiero", str(tmp_path / "nonexistent.csv"),
            ])

            # Typer's exists=True validator catches this before our code
            assert result.exit_code != 0

    def test_csv_with_results(self, tmp_path: Path) -> None:
        """CSV batch download displays results."""
        csv_file = tmp_path / "batch3.csv"
        csv_file.write_text("celoj\nhttps://youtu.be/abc\n")

        from typer.testing import CliRunner

        from A_medio.cli import app
        from A_medio.services.youtube import BatchResult

        runner = CliRunner()

        with patch("A_medio.cli.get_youtube_service") as mock_get:
            mock_service = MagicMock()
            mock_service.is_available.return_value = True
            mock_service.batch_download.return_value = [
                BatchResult(
                    row=1, url="https://youtu.be/abc", success=True,
                    files=[Path("/v/abc.mp4")],
                ),
            ]
            mock_get.return_value = mock_service

            result = runner.invoke(app, [
                "filmeto", "eljuti",
                "--csv-dosiero", str(csv_file),
            ])

            assert result.exit_code == 0
            assert "abc.mp4" in result.stdout

    def test_csv_no_url_needed(self, tmp_path: Path) -> None:
        """When using --csv-dosiero, URL argument is not required."""
        csv_file = tmp_path / "batch4.csv"
        csv_file.write_text("celoj\nhttps://youtu.be/abc\n")

        from typer.testing import CliRunner

        from A_medio.cli import app

        runner = CliRunner()

        with patch("A_medio.cli.get_youtube_service") as mock_get:
            mock_service = MagicMock()
            mock_service.is_available.return_value = True
            mock_service.batch_download.return_value = []
            mock_get.return_value = mock_service

            # No URL argument — should work because --csv-dosiero is provided
            result = runner.invoke(app, [
                "filmeto", "eljuti",
                "--csv-dosiero", str(csv_file),
            ])

            assert result.exit_code == 0
