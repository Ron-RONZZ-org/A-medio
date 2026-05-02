"""Tests for A_medio.config — plugin-level config wrapper."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from A_medio.config import get_download_dir, get_setting, set_download_dir, set_setting


class TestNamespacedSettings:
    """get_setting / set_setting wraps ``A.core.config`` with a prefix."""

    def test_get_setting_default(self) -> None:
        """get_setting delegates default value to ``_core_get``."""
        with patch("A_medio.config._core_get", return_value="bar") as mock_get:
            result = get_setting("foo", default="bar")
            mock_get.assert_called_once_with("A-medio.foo", "bar")
            assert result == "bar"

    def test_get_setting_stored(self) -> None:
        """get_setting returns stored value."""
        with patch("A_medio.config._core_get", return_value="stored_val") as mock_get:
            result = get_setting("baz")
            mock_get.assert_called_once_with("A-medio.baz", None)
            assert result == "stored_val"

    def test_set_setting(self) -> None:
        """set_setting delegates with prefix."""
        with patch("A_medio.config._core_set") as mock_set:
            set_setting("key_x", 42)
            mock_set.assert_called_once_with("A-medio.key_x", 42)

    def test_set_setting_string(self) -> None:
        """set_setting with string value."""
        with patch("A_medio.config._core_set") as mock_set:
            set_setting("download_dir", "/tmp/medio")
            mock_set.assert_called_once_with("A-medio.download_dir", "/tmp/medio")


class TestTypedAccessors:
    """Convenience accessors for known settings."""

    def test_get_download_dir_default(self) -> None:
        """get_download_dir computes default from ``data_dir / filmetoj``."""
        fake_data_dir = Path("/home/user/.local/share/A")
        expected = str(fake_data_dir / "filmetoj")

        with (
            patch("A_medio.config.get_setting", return_value=expected) as mock_get,
            patch("A_medio.config.data_dir", return_value=fake_data_dir),
        ):
            result = get_download_dir()

            mock_get.assert_called_once_with("download_dir", expected)
            assert result == expected

    def test_get_download_dir_custom(self) -> None:
        """get_download_dir returns stored value when set."""
        custom = "/custom/path"

        with patch("A_medio.config.get_setting", return_value=custom):
            result = get_download_dir()
            assert result == custom

    def test_set_download_dir(self) -> None:
        """set_download_dir delegates to set_setting."""
        with patch("A_medio.config.set_setting") as mock_set:
            set_download_dir("/movies")
            mock_set.assert_called_once_with("download_dir", "/movies")


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
