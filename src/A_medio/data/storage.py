"""Medio data layer - SQLite storage for video, photo, audio."""

from __future__ import annotations

from pathlib import Path

from A import ensure_dirs as _ensure_dirs
from A.data.base import SQLiteDB

_DATA_DIR: Path = Path.home() / ".local" / "share" / "A"

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

_CREATE_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_filmetoj_titolo ON filmetoj(titolo);
CREATE INDEX IF NOT EXISTS idx_fotoj_nomo ON fotoj(nomo);
CREATE INDEX IF NOT EXISTS idx_audioj_titolo ON audioj(titolo);
"""


def ensure_dirs() -> None:
    """Ensure data directory exists."""
    _ensure_dirs(_DATA_DIR)


def get_db(path: Path = _DATA_DIR / "medio.db") -> SQLiteDB:
    """Get database connection."""
    ensure_dirs()
    db = SQLiteDB(path)
    
    stmts = [
        _CREATE_FILMETOJ, _CREATE_FOTOJ, _CREATE_AUDIOJ,
        _CREATE_INDEXES,
    ]
    for stmt in stmts:
        db.execute(stmt)
    
    return db


__all__ = ["ensure_dirs", "get_db"]