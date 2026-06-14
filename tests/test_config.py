"""Tests for A_medio.config — plugin-level config wrapper."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from A.core.testing import patch_paths

from A_medio.config import get_download_dir, get_setting, set_download_dir, set_setting


@pytest.fixture(autouse=True)
def isolate(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Redirect A-core paths to temp dir for every test."""
    patch_paths(monkeypatch, tmp_path)


class TestNamespacedSettings:
    """get_setting / set_setting with legacy fallback."""

    def test_get_setting_default(self) -> None:
        """get_setting returns default when key not set."""
        result = get_setting("unknown", default="fallback")
        assert result == "fallback"

    def test_get_setting_stored_legacy(self) -> None:
        """get_setting reads from legacy schema when central is absent."""
        mock_legacy = MagicMock()
        mock_legacy.load.return_value = {"baz": "stored_val"}

        with patch("A_medio.config._legacy_schema", mock_legacy):
            result = get_setting("baz")

        assert result == "stored_val"

    def test_set_setting(self) -> None:
        """set_setting writes to central config."""
        from A.core.config import get_module_setting

        set_setting("key_x", 42)
        assert get_module_setting("filmeto", "key_x") == 42

    def test_set_setting_string(self) -> None:
        """set_setting with string value."""
        from A.core.config import get_module_setting

        set_setting("download_dir", "/tmp/medio")
        assert get_module_setting("filmeto", "download_dir") == "/tmp/medio"


class TestTypedAccessors:
    """Convenience accessors for known settings."""

    def test_get_download_dir_default(self) -> None:
        """get_download_dir returns default data_dir/filmetoj when not set."""
        from A.core.paths import data_dir

        result = get_download_dir()
        assert result == str(data_dir() / "filmetoj")

    def test_get_download_dir_central(self) -> None:
        """get_download_dir reads from central config ``filmeto.default_output``."""
        from A.core.config import set_module_setting

        set_module_setting("filmeto", "default_output", "/central/path")
        result = get_download_dir()
        assert result == "/central/path"

    def test_set_download_dir(self) -> None:
        """set_download_dir writes to central config."""
        from A.core.config import get_module_setting

        set_download_dir("/movies")
        assert get_module_setting("filmeto", "default_output") == "/movies"


class TestCLIConfigCommands:
    """Integration-style tests using Typer CliRunner."""

    def test_config_get_not_set(self) -> None:
        """``medio config get <key>`` reports when unset."""
        from typer.testing import CliRunner

        from A_medio.cli import app

        runner = CliRunner()

        with patch("A_medio.cli.get_setting", return_value=None):
            result = runner.invoke(app, ["config", "get", "nonexistent"])

        assert result.exit_code == 0
        assert "ne estas difinita" in result.stdout or "not set" in result.stdout

    def test_config_get_set(self) -> None:
        """``medio config get <key>`` shows value when set."""
        from typer.testing import CliRunner

        from A_medio.cli import app

        runner = CliRunner()

        with patch("A_medio.cli.get_setting", return_value="/data/vids"):
            result = runner.invoke(app, ["config", "get", "download_dir"])

        assert result.exit_code == 0
        assert "/data/vids" in result.stdout

    def test_config_set(self) -> None:
        """``medio config set <key> <value>`` stores the value."""
        from typer.testing import CliRunner

        from A_medio.cli import app

        runner = CliRunner()

        with patch("A_medio.cli.set_setting") as mock_set:
            result = runner.invoke(app, ["config", "set", "download_dir", "/videos"])

        assert result.exit_code == 0
        mock_set.assert_called_once_with("download_dir", "/videos")
        assert "agordita" in result.stdout or "saved" in result.stdout
