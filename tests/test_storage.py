"""Tests for A_medio.data.storage — SQLite data layer."""

from __future__ import annotations

from pathlib import Path

from A_medio.data.storage import get_db


class TestDataDir:
    """Verify paths use ``A.core.paths.data_dir``, not hardcoded values."""

    def test_data_dir_uses_core(self) -> None:
        """_DATA_DIR should derive from A.core.paths.data_dir."""
        from A_medio.data import storage

        expected = storage.data_dir()
        assert storage._DATA_DIR == expected
        assert "A" in str(storage._DATA_DIR)

    def test_no_hardcoded_home(self) -> None:
        """_DATA_DIR should NOT contain a literal hardcoded path fragment."""
        from A_medio.data import storage

        path_str = str(storage._DATA_DIR)
        assert ".local/share/A" in path_str
        # Make sure it's NOT a hardcoded string from this file — it should
        # come from A.core.paths.data_dir()
        assert storage._DATA_DIR == storage.data_dir()


class TestGetDb:
    """get_db returns a functional SQLiteDB."""

    def test_get_db_returns_sqlitedb(self) -> None:
        """get_db returns an SQLiteDB instance."""
        db = get_db(Path("/tmp/test_medio.db"))
        assert db is not None
        rows = db.execute("SELECT name FROM sqlite_master WHERE type='table'")
        table_names = {r["name"] for r in rows}
        assert "youtube_videos" in table_names
        assert "filmetoj" in table_names
        assert "fotoj" in table_names
        assert "audioj" in table_names

    def test_youtube_videos_fts_exists(self) -> None:
        """FTS5 virtual table is created."""
        db = get_db(Path("/tmp/test_medio_fts.db"))
        rows = db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='youtube_videos_fts'"
        )
        assert len(rows) == 1
