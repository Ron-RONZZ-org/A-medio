"""Medio data layer - SQLite storage for video, photo, audio."""

from __future__ import annotations

from pathlib import Path

from A.core.paths import data_dir
from A.data.base import SQLiteDB, backup_db, health_check


def ensure_dirs() -> None:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)


def get_db(path: Path = _DATA_DIR / "medio.db") -> SQLiteDB:
    """Get database connection with health check and backup."""
    ensure_dirs()
    if not health_check(path):
        from A.data.base import repair_db as _repair
        _repair(path)
    backup_db(path)
    db = SQLiteDB(path)

    stmts = [
        _CREATE_YOUTUBE_VIDEOS,
        _CREATE_YOUTUBE_VIDEOS_FTS,
        _CREATE_FILMETOJ,
        _CREATE_FOTOJ,
        _CREATE_AUDIOJ,
        _IDX_FILMETOJ_TITOLO,
        _IDX_FOTOJ_NOMO,
        _IDX_AUDIOJ_TITOLO,
    ]
    for stmt in stmts:
        db.execute(stmt)

    return db


__all__ = ["ensure_dirs", "get_db"]