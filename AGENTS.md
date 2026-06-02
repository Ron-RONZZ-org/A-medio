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
│   └── youtube/     # YouTube-specific service (yt-dlp wrapper)
│       ├── __init__.py         # Package re-exports
│       ├── service.py          # YouTubeService (~283 lines)
│       ├── _wrapper.py         # YtDlpWrapper lazy import singleton
│       ├── _models.py          # YouTubeVideo, BatchResult, EstimateResult
│       ├── _format_helpers.py  # build_format_selector, build_subtitle_opts
│       ├── _cookie_helpers.py  # Cookie/browser auth helpers
│       ├── _strategy.py        # Search strategy persistence
│       └── _csv_helpers.py     # CSV batch download parsing
└── data/
    └── storage.py   # SQLite (uses A.data.base)
```

### UUID Exception: `youtube_videos`

The `youtube_videos` table uses `INTEGER PRIMARY KEY AUTOINCREMENT` (not `uuid TEXT PRIMARY KEY`)
because it is a **transient search-result cache** imported from yt-dlp, not a user-facing editable
entity. There are no cross-references to this table from other modules. Per workspace UUID PK rule,
exceptions must be documented. A nullable `uuid TEXT` column exists for future migration.

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

**Retry strategy:** All yt-dlp operations (search, estimate, download) try multiple
cookie sources in order. A shared helper ``_build_cookie_candidates()`` in
``service.py`` builds the candidate list:

1. Explicit ``--kuketoj`` file (if provided)
2. Browser cookies (explicit flag ``--kuketoj-de-retumilo`` or config fallback)
3. No cookies (bare fallback)

**Search** additionally probes auto-discovered browser profiles and the cached
search strategy before falling back. Certificate errors and empty results trigger
automatic retries in search.

**Estimate** (``estimate()``) tries each candidate in order. If one succeeds
(returns a non-``None`` info dict), its result is used. If all candidates fail,
returns ``None`` with an error message from the last exception. Single-entry
playlist wrapping from yt-dlp is unwrapped automatically.

**Download** (``download()``) tries each candidate in order. If a candidate
produces files (diff from ``before`` snapshot), it is considered successful and
the loop breaks. If no files are created and an error was captured, the last
error is shown. If no files are created without error, ``"Neniu dosiero
elŝutita."`` is shown.

**Important:** Config-saved browser fork names (``floorp``, ``librewolf``, etc.)
are mapped to their yt-dlp-compatible base name (``firefox``) via
``_BROWSER_FORK_MAP`` before being passed to yt-dlp's ``cookiesfrombrowser``.
The explicit CLI flag path uses ``_parse_cookies_from_browser()`` which maps
correctly; the config path in ``_cookie_browser_candidates()`` does the same
mapping via ``mapped_browser = _BROWSER_FORK_MAP.get(raw_browser, raw_browser)``.

**Auto cookie setup on first call:**
On the first ``serci`` or ``elsuti`` (single-URL) call without ``--kuketoj`` or
``--kuketoj-de-retumilo`` flags **and** no browser saved in config yet:
1. ``_auto_setup_cookies()`` in ``cli.py`` calls ``_detect_available_browsers()`` to probe all Firefox-style browser roots
2. If a browser with ``cookies.sqlite`` is found, prompts the user: *"Detected Floorp cookies from ~/.floorp/xxx.default. Use for YouTube?"*
3. On confirmation, saves the browser (and optional profile path) to persistent config
4. Future calls auto-load from config — no prompt
5. Uses ``A.utils.interactive.confirm_action`` for the prompt
6. Non-interactive terminals (piped, scripted) skip auto-setup silently
7. Explicit ``--kuketoj`` or ``--kuketoj-de-retumilo`` flags always take precedence over config

**Important:** The guard uses ``get_cookies_from_browser()`` (config-stored browser), NOT
``_load_search_strategy()``. This prevents a scenario where search succeeds without
cookies (returning partial metadata) and caches a strategy, which would otherwise
block the cookie prompt on subsequent ``elsuti`` calls.

**Config keys:**
- ``cookies_from_browser`` (str|None) — browser name saved from auto-setup
- ``cookies_from_browser_profile`` (str|None) — specific profile path (when null, yt-dlp auto-selects)

**CLI:** ``kuketoj-helpo`` command shows detailed setup instructions.

### Download Confirmation

Before downloading via ``elsuti`` (non-CSV, non-``--taksi`` mode):
1. ``_download_with_confirmation()`` in ``cli.py`` calls ``youtube.estimate()`` to dry-run and get file sizes
2. Shows a Rich table with Title, Duration, and Size columns
3. Prompts: *"Continue with download?"* with default Yes
4. On confirmation, proceeds with the actual download
5. Non-interactive terminals skip the prompt and download directly

### Output Path Resolution (``--output``/``-o``)

The ``--output``/``-o`` flag accepts file or directory paths and resolves them
via ``_resolve_output_template()`` in ``cli.py``:

| Input | Behaviour |
|-------|-----------|
| ``-o /videos/`` | Existing directory → default filename ``%(title).80s [%(id)s].%(ext)s`` |
| ``-o video.mp4`` | File path → parent as directory, filename template ``video.%(ext)s`` |
| ``-o ~/videos/`` | Trailing slash → create directory, default template |
| ``-o /path/to/newfolder`` | Non-existent, no ext, >1 part, parent also non-existent → create directory, default template |
| ``-o /existing/parent/barename`` | Parent exists, no ext → file template ``barename.%(ext)s`` — use trailing ``/`` for directory |
| ``-o myvideo`` | Relative, single part, no ext → file template ``myvideo.%(ext)s`` |

When omitted, falls back to configured download directory with default template.

### Download Estimation

``--taksi`` flag on ``medio filmeto elsuti`` runs a dry-run ``extract_info``
and shows estimated item count + total file size without downloading.

### Search Extras

| Flag | Command | Effect |
|------|---------|--------|
| ``--aldona`` / ``-a`` | ``serci`` | Show views, subscribers, duration |
| ``--playlistoj`` / ``-P`` | ``serci`` | Search for playlists |
| ``--limo`` / ``-lo`` | ``elsuti`` | Max items from a playlist |

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

**CLI usage:** ``medio filmeto elsuti --csv-dosiero elsutoj.csv``

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
| Cookie/browser auth + auto-setup | ✅ [#6](https://github.com/Ron-RONZZ-org/A-medio/issues/6) | Done |
| Download confirmation prompt | ✅ (this PR) | Done |
| `ludi` (play video) | ❌ [#7](https://github.com/Ron-RONZZ-org/A-medio/issues/7) | Won't do — users can ``elsuti --output /tmp && xdg-open`` |
| Download size estimation | ✅ [#8](https://github.com/Ron-RONZZ-org/A-medio/issues/8) | Done |
| Search extras (`--aldona`, `--playlistoj`, `--limo`) | ✅ [#9](https://github.com/Ron-RONZZ-org/A-medio/issues/9) | Done |



## Package Manager: `uv` is Required

All A-ecosystem development **must** use `uv` as the package manager:

| Operation | Command |
|-----------|---------|
| Install dependencies | `uv pip install <pkg>` |
| Install project in dev mode | `uv pip install -e .` |
| Run tests | `uv run pytest tests/` |
| Install CLI tools (poetry, etc.) | `uv tool install <tool>` |
| Add dev dependency | `uv add --dev <pkg>` |

**Exceptions:**
- `pip` in README install instructions is acceptable for end users who may not have `uv`
- Readthedocs platform build may require `pip` (platform constraint)
- Runtime `install-on-confirmation` code may fall back to `pip` if `uv` is unavailable (see A-core AGENTS.md)

## What to Avoid

- Don't duplicate A-core utilities
- Don't skip i18n (use `tr()`)
- Don't use `print()` — use `A` output functions
- Don't hardcode paths — use `A.core.paths`
- Don't implement utilities that should be in core
## Branch Convention

All A-* repos use `main` as the primary branch. Use `main` for all development.
