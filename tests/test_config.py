"""Tests for A_medio.config — plugin-level config wrapper."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from A_medio.config import get_download_dir, get_setting, set_download_dir, set_setting


class TestNamespacedSettings:
    """get_setting / set_setting uses ``_schema`` (ConfigSchema)."""

    def test_get_setting_default(self) -> None:
        """get_setting returns default when key not in schema."""
        mock_schema = MagicMock()
        mock_schema.load.return_value = {"other_key": "bar"}

        with patch("A_medio.config._schema", mock_schema):
            result = get_setting("unknown", default="fallback")

        assert result == "fallback"

    def test_get_setting_stored(self) -> None:
        """get_setting returns stored value from schema."""
        mock_schema = MagicMock()
        mock_schema.load.return_value = {"baz": "stored_val"}

        with patch("A_medio.config._schema", mock_schema):
            result = get_setting("baz")

        assert result == "stored_val"

    def test_set_setting(self) -> None:
        """set_setting saves via schema."""
        mock_schema = MagicMock()
        mock_schema.load.return_value = {}

        with patch("A_medio.config._schema", mock_schema):
            set_setting("key_x", 42)

        mock_schema.save.assert_called_once()
        # verify the merged dict includes the new key
        saved = mock_schema.save.call_args[0][0]
        assert saved["key_x"] == 42

    def test_set_setting_string(self) -> None:
        """set_setting with string value."""
        mock_schema = MagicMock()
        mock_schema.load.return_value = {}

        with patch("A_medio.config._schema", mock_schema):
            set_setting("download_dir", "/tmp/medio")

        saved = mock_schema.save.call_args[0][0]
        assert saved["download_dir"] == "/tmp/medio"


class TestTypedAccessors:
    """Convenience accessors for known settings."""

    def test_get_download_dir_default(self) -> None:
        """get_download_dir uses schema default when key is not set."""
        mock_schema = MagicMock()
        mock_schema.load.return_value = {}
        mock_schema.default.return_value = "/default/path/filmetoj"

        with patch("A_medio.config._schema", mock_schema):
            result = get_download_dir()

        assert result == "/default/path/filmetoj"

    def test_get_download_dir_custom(self) -> None:
        """get_download_dir returns stored value when set."""
        mock_schema = MagicMock()
        mock_schema.load.return_value = {"download_dir": "/custom/path"}

        with patch("A_medio.config._schema", mock_schema):
            result = get_download_dir()

        assert result == "/custom/path"

    def test_set_download_dir(self) -> None:
        """set_download_dir saves via schema."""
        mock_schema = MagicMock()
        mock_schema.load.return_value = {}

        with patch("A_medio.config._schema", mock_schema):
            set_download_dir("/movies")

        saved = mock_schema.save.call_args[0][0]
        assert saved["download_dir"] == "/movies"


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
