"""Medio data layer - SQLite storage for video, photo, audio."""

from __future__ import annotations

from pathlib import Path

from A.core.paths import data_dir
from A.data.base import SQLiteDB, backup_db, health_check


_DATA_DIR = data_dir() / "medio"

# ──────────────────────────────────────────────────────────────────────────────
# YouTube videos (cached search results)
#
# NOTE: This table uses INTEGER PRIMARY KEY AUTOINCREMENT (not uuid TEXT
# PRIMARY KEY) because it's a transient search-result cache imported from
# yt-dlp, not a user-facing editable entity. There are no cross-references
# to this table from other modules. The uuid column exists for future
# migration if needed. See workspace AGENTS.md "UUID primary key" rule for
# exception policy.
# ──────────────────────────────────────────────────────────────────────────────

_CREATE_YOUTUBE_VIDEOS = """
CREATE TABLE IF NOT EXISTS youtube_videos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    uuid TEXT,
    video_id TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    author TEXT NOT NULL DEFAULT '',
    duration INTEGER NOT NULL DEFAULT 0,
    view_count INTEGER NOT NULL DEFAULT 0,
    upload_date TEXT NOT NULL DEFAULT '',
    thumbnail_url TEXT NOT NULL DEFAULT '',
    url TEXT NOT NULL,
    kreita_je TEXT NOT NULL,
    modifita_je TEXT NOT NULL
);
"""

_CREATE_YOUTUBE_VIDEOS_FTS = """
CREATE VIRTUAL TABLE IF NOT EXISTS youtube_videos_fts USING fts5(
    title,
    description,
    author,
    content='youtube_videos',
    content_rowid='id'
);
"""

# ──────────────────────────────────────────────────────────────────────────────
# Videos (filmeto)
# ──────────────────────────────────────────────────────────────────────────────

_CREATE_FILMETOJ = """
CREATE TABLE IF NOT EXISTS filmetoj (
    uuid TEXT PRIMARY KEY,
    titolo TEXT NOT NULL,
    url TEXT NOT NULL,
    fonte TEXT NOT NULL DEFAULT 'youtube',
    lungo INTEGER NOT NULL DEFAULT 0,
    priskribo TEXT NOT NULL DEFAULT '',
    etikedoj TEXT NOT NULL DEFAULT '[]',
    loko TEXT NOT NULL DEFAULT '',
    stato TEXT NOT NULL DEFAULT 'ne_legita',
    kreita_je TEXT NOT NULL,
    modifita_je TEXT NOT NULL
);
"""

# ──────────────────────────────────────────────────────────────────────────────
# Photos (foto)
# ──────────────────────────────────────────────────────────────────────────────

_CREATE_FOTOJ = """
CREATE TABLE IF NOT EXISTS fotoj (
    uuid TEXT PRIMARY KEY,
    nomo TEXT NOT NULL,
    vojo TEXT NOT NULL,
    dosiertipo TEXT NOT NULL DEFAULT '',
    grandeco INTEGER NOT NULL DEFAULT 0,
    dato TEXT NOT NULL DEFAULT '',
    etikedoj TEXT NOT NULL DEFAULT '[]',
    loko TEXT NOT NULL DEFAULT '',
    kreita_je TEXT NOT NULL,
    modifita_je TEXT NOT NULL
);
"""

# ──────────────────────────────────────────────────────────────────────────────
# Audio/podcasts (audio)
# ──────────────────────────────────────────────────────────────────────────────

_CREATE_AUDIOJ = """
CREATE TABLE IF NOT EXISTS audioj (
    uuid TEXT PRIMARY KEY,
    titolo TEXT NOT NULL,
    url TEXT NOT NULL,
    fonte TEXT NOT NULL DEFAULT 'podcast',
    lungo INTEGER NOT NULL DEFAULT 0,
    priskribo TEXT NOT NULL DEFAULT '',
    etikedoj TEXT NOT NULL DEFAULT '[]',
    loko TEXT NOT NULL DEFAULT '',
    stato TEXT NOT NULL DEFAULT 'ne_legita',
    kreita_je TEXT NOT NULL,
    modifita_je TEXT NOT NULL
);
"""

# ──────────────────────────────────────────────────────────────────────────────
# Indexes
# ──────────────────────────────────────────────────────────────────────────────

_IDX_FILMETOJ_TITOLO = "CREATE INDEX IF NOT EXISTS idx_filmetoj_titolo ON filmetoj(titolo);"
_IDX_FOTOJ_NOMO = "CREATE INDEX IF NOT EXISTS idx_fotoj_nomo ON fotoj(nomo);"
_IDX_AUDIOJ_TITOLO = "CREATE INDEX IF NOT EXISTS idx_audioj_titolo ON audioj(titolo);"


def ensure_dirs() -> None:
    """Ensure data directory exists."""
    _DATA_DIR.mkdir(parents=True, exist_ok=True)


def get_db(path: Path | None = None) -> SQLiteDB:
    """Get database connection with health check and backup."""
    if path is None:
        path = _DATA_DIR / "medio.db"
    ensure_dirs()
    if not health_check(path):
        from A.data.base import repair_db as _repair
        _repair(path)
    backup_db(path)
    db = SQLiteDB(path)

    # Create tables
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

    # Migration: add uuid column to youtube_videos for existing databases
    _migrate_youtube_videos_uuid(db)

    return db


def _migrate_youtube_videos_uuid(db: SQLiteDB) -> None:
    """Add uuid column to youtube_videos table if missing."""
    try:
        # Check if column exists
        cols = db.execute("PRAGMA table_info(youtube_videos)")
        col_names = {c["name"] for c in cols}
        if "uuid" not in col_names:
            db.execute("ALTER TABLE youtube_videos ADD COLUMN uuid TEXT")
    except Exception:
        pass  # Table might not exist yet


__all__ = ["ensure_dirs", "get_db"]
