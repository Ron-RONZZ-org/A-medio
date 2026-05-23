"""Tests for A_medio.data.storage — SQLite data layer."""

from __future__ import annotations

from pathlib import Path

from A_medio.data.storage import get_db


class TestDataDir:
    """Verify paths use ``A.core.paths.data_dir``, not hardcoded values."""

    def test_data_dir_derives_from_core(self) -> None:
        """_DATA_DIR should be set from data_dir() at import time."""
        from A_medio.data import storage

        # Both sides should match (data_dir is overridden by isolation fixture
        # in test context, but the relationship still holds)
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

    def test_youtube_videos_has_uuid_column(self) -> None:
        """youtube_videos table has uuid column for future UUID support."""
        db = get_db(Path("/tmp/test_medio_uuid.db"))
        cols = db.execute("PRAGMA table_info(youtube_videos)")
        col_names = {c["name"] for c in cols}
        assert "uuid" in col_names

    def test_youtube_videos_uuid_migration_idempotent(self) -> None:
        """Calling get_db twice does not break on the uuid column."""
        db1 = get_db(Path("/tmp/test_medio_migrate.db"))
        db2 = get_db(Path("/tmp/test_medio_migrate.db"))
        # Both should return functional db without errors
        cols = db2.execute("PRAGMA table_info(youtube_videos)")
        col_names = {c["name"] for c in cols}
        assert "uuid" in col_names
