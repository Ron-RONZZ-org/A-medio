# AGENTS.md — Rules for A-medio
This file extends [A-workspace](./workspace/AGENTS.md).

This file extends root A-core AGENTS.md for the A-medio plugin.

## Relationship to A-core

**A-medio depends on A-core** for:
- `A` package imports (i18n, output, subprocess, SQLite)
- Plugin discovery via entry points
- Shared utilities
- **API Reference**: See [A-core AGENTS.md](https://github.com/Ron-RONZZ-org/A-core/blob/main/AGENTS.md#api-reference)

**All source code must import from `A`, never duplicate utilities.**

## Combined Plugin

A-medio combines media types:
- filmeto (video)
- foto (photo)
- audio (audio/podcast)

This is intentional — they share the same SQLite database.

## Optional Dependencies

External tools may require runtime detection:
- `yt-dlp` for YouTube/video downloads
- `ffprobe` for media metadata

Use `A.utils.run` with `shutil.which()` to detect availability.

## If You Need Something in Core

If you need a utility that should be in A-core:

1. **Search existing issues** on [A-core](https://github.com/Ron-RONZZ-org/A-core/issues)
2. **Create an issue** describing the need
3. **Wait for core enhancement** before implementing locally
4. **Use feature detection** when available

## Architecture

```
src/A_medio/
├── __init__.py       # Plugin exports
├── cli.py           # Typer app with subcommands
├── config.py        # Plugin-level config (namespaced under A.config)
├── services/
│   ├── __init__.py  # Service exports
│   ├── base.py      # Base MediaService interface
│   └── youtube.py   # YouTube-specific service (yt-dlp wrapper)
└── data/
    └── storage.py   # SQLite (uses A.data.base)
```

### Service Pattern

Each media type has its own service file:
- `services/youtube.py` — YouTube video search + download via yt-dlp
- Future: `services/photo.py`, `services/audio.py`

Services implement `MediaService` base class with:
- `is_available()` — runtime detection
- `search()` — search with filters
- `get_by_id()` — retrieve by ID
- `download()` — download media with format/subtitle options

### yt-dlp Wrapper (`services/youtube.py`)

Uses the **yt-dlp Python library** (not subprocess) for all operations:

| Component | Purpose |
|-----------|---------|
| `YtDlpWrapper` | Singleton with lazy import + availability detection |
| `YouTubeVideo` | Data object for search results |
| `YouTubeService` | Search, download, local cache via CRUDService |
| `build_format_selector()` | Build format strings (resolution, audio-only, video-only) |
| `build_subtitle_opts()` | Build subtitle options (auto, all, or specific langs) |

**Format selection:**
- `bestaudio` — audio-only extraction
- `bestvideo[height<=N]` — video stream only
- `best[height<=N]` — combined stream with resolution cap

**Subtitle options:**
- `auto` / `all` — download all available subtitles
- Comma-separated language codes (e.g. `eo,en,fr`)

### Cookie / Browser Auth

Two sources supported, passed as yt-dlp options:

| CLI flag | yt-dlp option | Example |
|---|---|---|
| ``--kuketoj <path>`` | ``cookiefile`` | ``--kuketoj /tmp/cookies.txt`` |
| ``--kuketoj-de-retumilo <browser>[:<profile>]`` | ``cookiesfrombrowser`` | ``--kuketoj-de-retumilo floorp`` |

**Retry strategy:** Search tries multiple cookie sources in order:
1. Cached successful strategy (from previous search)
2. Explicit ``--kuketoj`` file
3. Auto-discovered browser profiles (Firefox forks: floorp, librewolf, waterfox, zen)
4. No cookies (bare fallback)

Certificate errors and empty results trigger automatic fallback retries.

**CLI:** ``kuketoj-helpo`` command shows detailed setup instructions.

### CSV Batch Download

``parse_csv_rows()`` parses CSV files into download specs for batch processing:

**Supported columns:**

| Header (Esperanto) | English Alias | Type |
|---|---|---|
| `celoj` | `targets` | URL(s) — space/comma/semicolon separated |
| `difino` | `resolution` | int (max video height) |
| `sonkvalito` | `audio_bitrate` | int (kbps) |
| `audio` | — | bool (1/0, true/false, jes/ne) |
| `filmeto` | `video_only` | bool |
| `vojo` | `output_dir` | str (path) |
| `subtitoloj` | `subtitles` | str (comma-separated langs) |

**CLI usage:** ``medio filmeto eljuti --csv-dosiero elsutoj.csv``

CLI flags (``--difino``, ``--audio``, etc.) serve as default values inherited by all CSV rows.

### FTS5 Search

YouTube videos use FTS5 for full-text search on:
- title
- description
- author

Results are cached in SQLite for offline search via `--local` flag.

## Code Standards

1. Use `tr()` for all user-facing strings
2. Use `error()` for errors, `info()` for info
3. Type hints on all public functions
4. Docstrings on all public functions
5. Tests required for all modules
6. Use WAL mode for SQLite

## Known Gaps (Not Yet Ported from Legacy)

| Feature | Issue | Priority |
|---------|-------|----------|
| Cookie/browser auth | ✅ [#6](https://github.com/Ron-RONZZ-org/A-medio/issues/6) | Done |
| `ludi` (play video in temp dir) | [#7](https://github.com/Ron-RONZZ-org/A-medio/issues/7) | Medium |
| Download size estimation | [#8](https://github.com/Ron-RONZZ-org/A-medio/issues/8) | Low |
| Search enhancements (`--aldona`, `--playlistoj`, `--limo`) | [#9](https://github.com/Ron-RONZZ-org/A-medio/issues/9) | Low |

## What to Avoid

- Don't duplicate A-core utilities
- Don't skip i18n (use `tr()`)
- Don't use `print()` — use `A` output functions
- Don't hardcode paths — use `A.core.paths`
- Don't implement utilities that should be in core
## Branch Convention

All A-* repos use `main` as the primary branch. Use `main` for all development.
