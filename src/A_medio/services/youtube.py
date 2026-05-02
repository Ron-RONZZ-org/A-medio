"""YouTube media service using yt-dlp."""

from __future__ import annotations

import csv
import json
import re
import shutil
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Generator

from A import error, info, tr, tr_multi
from A.core.paths import data_dir
from A.core.service import CRUDService
from A.data.search import FTSConfig
from A.utils.normalize import fold_search_text

from A_medio.config import get_download_dir
from A_medio.services.base import MediaService
from A_medio.data.storage import get_db

if TYPE_CHECKING:
    from yt_dlp import YoutubeDL
    from yt_dlp.utils import DownloadError


# ──────────────────────────────────────────────────────────────────────────────
# Lazy imports for yt-dlp (avoids import overhead when not used)
# ──────────────────────────────────────────────────────────────────────────────

_ytdl_class: type[YoutubeDL] | None = None
_download_error_class: type[DownloadError] | None = None


def _get_ytdl_class() -> type[YoutubeDL]:
    """Lazy import ``yt_dlp.YoutubeDL``.

    Returns:
        The ``YoutubeDL`` class.
    """
    global _ytdl_class
    if _ytdl_class is None:
        from yt_dlp import YoutubeDL  # type: ignore[import-untyped]
        _ytdl_class = YoutubeDL
    return _ytdl_class


def _get_download_error() -> type[DownloadError]:
    """Lazy import ``yt_dlp.utils.DownloadError``.

    Returns:
        The ``DownloadError`` exception class.
    """
    global _download_error_class
    if _download_error_class is None:
        from yt_dlp.utils import DownloadError  # type: ignore[import-untyped]
        _download_error_class = DownloadError
    return _download_error_class


# ──────────────────────────────────────────────────────────────────────────────
# Format selector helpers
# ──────────────────────────────────────────────────────────────────────────────


def build_format_selector(
    resolution: int | None = None,
    audio_only: bool = False,
    video_only: bool = False,
    audio_bitrate: int | None = None,
) -> str:
    """Build a yt-dlp format selector string.

    Args:
        resolution: Max video height (e.g. 720, 1080). ``None`` means best.
        audio_only: If True, select best audio stream only.
        video_only: If True, select best video stream only (no audio).
        audio_bitrate: Max audio bitrate in kbps (only when ``audio_only``).

    Returns:
        A yt-dlp format string like ``"best[height<=1080]/best"``.

    Raises:
        ValueError: If both ``audio_only`` and ``video_only`` are True.
    """
    if audio_only and video_only:
        raise ValueError("Cannot use both audio-only and video-only.")

    if audio_only:
        if audio_bitrate is not None:
            return f"bestaudio[abr<={int(audio_bitrate)}]/bestaudio"
        return "bestaudio"

    if video_only:
        if resolution is not None:
            return f"bestvideo[height<={int(resolution)}]/bestvideo"
        return "bestvideo"

    if resolution is not None:
        return f"best[height<={int(resolution)}]/best"
    return "best"


def build_subtitle_opts(subtitles: str | None) -> dict[str, Any]:
    """Build yt-dlp options for subtitle downloading.

    Args:
        subtitles: Subtitle spec:
            - ``"auto"`` or ``"all"``: download all available subtitles.
            - Comma-separated language codes (e.g. ``"eo,en,fr"``).

    Returns:
        Dict of yt-dlp options, or empty dict if *subtitles* is falsy.
    """
    if not subtitles:
        return {}

    spec = subtitles.strip().lower()
    opts: dict[str, Any] = {
        "writesubtitles": True,
        "writeautomaticsub": spec in {"auto", "all"},
        "subtitlesformat": "best",
    }
    if spec not in {"auto", "all"}:
        langs = [x.strip() for x in subtitles.split(",") if x.strip()]
        if langs:
            opts["subtitleslangs"] = langs
    return opts


# ──────────────────────────────────────────────────────────────────────────────
# CSV batch download support
# ──────────────────────────────────────────────────────────────────────────────

# Mapping of CSV column headers → internal option keys.
# Esperanto names preferred; English aliases accepted.
_CSV_HEADER_MAP: dict[str, str] = {
    # targets (required)
    "celoj": "targets",
    "targets": "targets",
    "target": "targets",
    "url": "targets",
    "urls": "targets",
    # resolution
    "difino": "resolution",
    "rezolucio": "resolution",
    "resolution": "resolution",
    # audio bitrate
    "sonkvalito": "audio_bitrate",
    "audio_bitrate": "audio_bitrate",
    "bitrate": "audio_bitrate",
    # bool flags
    "audio": "audio_only",
    "filmeto": "video_only",
    "video_only": "video_only",
    # output directory
    "vojo": "output_dir",
    "output_dir": "output_dir",
    "output": "output_dir",
    "path": "output_dir",
    "directory": "output_dir",
    # subtitles
    "subtitoloj": "subtitles",
    "subtitles": "subtitles",
    "subs": "subtitles",
    # cookies
    "kuketoj": "cookies",
    "cookies": "cookies",
    "cookie_file": "cookies",
    "kuketoj_de_retumilo": "cookies_from_browser",
    "cookies_from_browser": "cookies_from_browser",
}

_CSV_TRUE_VALUES: frozenset[str] = frozenset({"1", "true", "yes", "y", "jes", "j"})
_CSV_FALSE_VALUES: frozenset[str] = frozenset({"0", "false", "no", "n", "ne"})


def _csv_effective_cell(raw: object) -> str | None:
    """Return stripped text or ``None`` for empty/null cells."""
    text = str(raw or "").strip()
    if not text:
        return None
    if text.lower() in {"null", "none", "nil"}:
        return None
    return text


def _normalize_csv_header(raw: str) -> str | None:
    """Normalise a CSV column header to an internal option key.

    Args:
        raw: Raw header string.

    Returns:
        Internal key name, or ``None`` if unrecognised.
    """
    key = raw.strip().lower().replace("-", "_").replace(" ", "_")
    return _CSV_HEADER_MAP.get(key)


def _parse_csv_bool(value: str, *, field: str, row: int) -> bool:
    """Parse a CSV cell as a boolean.

    Args:
        value: Cell text.
        field: Field name (for error messages).
        row: Row number (for error messages, 1-indexed).

    Returns:
        True or False.

    Raises:
        ValueError: If value is not a recognised boolean.
    """
    normalized = value.strip().lower()
    if normalized in _CSV_TRUE_VALUES:
        return True
    if normalized in _CSV_FALSE_VALUES:
        return False
    raise ValueError(
        f"CSV vico {row}: nevalida valoro por '{field}': {value!r}. "
        f"Uzu jes/ne aŭ true/false."
    )


def parse_csv_rows(
    csv_path: str | Path,
    initial_state: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Parse a CSV file into a list of download specs.

    The CSV **must** have a ``celoj`` (targets) column.  Each row
    specifies download options; empty cells inherit from the previous
    row (or from *initial_state* for the first row).

    Supported columns (Esperanto / English):

    ==============  =======================  ===========
    Header          Key                      Type
    ==============  =======================  ===========
    ``celoj``       ``targets``              URL string(s)
    ``difino``      ``resolution``           int
    ``sonkvalito``  ``audio_bitrate``        int
    ``audio``       ``audio_only``           bool
    ``filmeto``     ``video_only``           bool
    ``vojo``        ``output_dir``           str
    ``subtitoloj``  ``subtitles``            str
    ``kuketoj``     ``cookies``              str (path to cookies.txt)
    ``kuketoj_de_retumilo``  ``cookies_from_browser``  str
    ==============  =======================  ===========

    Args:
        csv_path: Path to the CSV file.
        initial_state: Default values inherited by all rows.

    Returns:
        List of download-spec dicts, each with at least a ``"targets"`` key.

    Raises:
        FileNotFoundError: If the CSV file does not exist.
        ValueError: If required columns are missing or cell parsing fails.
    """
    path = Path(csv_path)
    if not path.exists():
        raise FileNotFoundError(f"CSV-dosiero ne trovita: {path}")

    state: dict[str, Any] = dict(initial_state or {})
    rows: list[dict[str, Any]] = []

    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        headers = list(reader.fieldnames or [])
        if not headers:
            raise ValueError("CSV-dosiero estas malplena (neniu kaprubriko).")

        # Map headers to internal keys
        mapped: dict[str, str] = {}
        for header in headers:
            key = _normalize_csv_header(header)
            if key:
                mapped[header] = key

        if "targets" not in mapped.values():
            raise ValueError(
                "CSV-dosiero devas havi kolumnon 'celoj' (URL-oj). "
                f"Trovitaj: {', '.join(headers)}"
            )

        for row_number, row in enumerate(reader, start=2):
            if not isinstance(row, dict):
                continue

            for raw_header, option_key in mapped.items():
                cell = _csv_effective_cell(row.get(raw_header))
                if cell is None:
                    continue

                if option_key == "targets":
                    # Split on whitespace, comma, or semicolon
                    targets = [
                        t for t in re.split(r"[\s,;]+", cell) if t
                    ]
                    if not targets:
                        raise ValueError(
                            f"CSV vico {row_number}: malplena 'celoj'."
                        )
                    state["targets"] = targets

                elif option_key in {"audio_only", "video_only"}:
                    state[option_key] = _parse_csv_bool(
                        cell, field=option_key, row=row_number,
                    )

                elif option_key in {"resolution", "audio_bitrate"}:
                    try:
                        state[option_key] = int(cell)
                    except ValueError as exc:
                        raise ValueError(
                            f"CSV vico {row_number}: nevalida nombro por "
                            f"'{option_key}': {cell!r}."
                        ) from exc

                elif option_key in {"output_dir", "subtitles", "cookies", "cookies_from_browser"}:
                    state[option_key] = cell

            # Ensure targets exist
            targets = state.get("targets")
            if not isinstance(targets, list) or not targets:
                raise ValueError(
                    f"CSV vico {row_number}: mankas valida 'celoj'."
                )

            rows.append({
                "targets": list(targets),
                "resolution": state.get("resolution"),
                "audio_bitrate": state.get("audio_bitrate"),
                "audio_only": bool(state.get("audio_only", False)),
                "video_only": bool(state.get("video_only", False)),
                "output_dir": state.get("output_dir"),
                "subtitles": state.get("subtitles"),
                "cookies": state.get("cookies"),
                "cookies_from_browser": state.get("cookies_from_browser"),
            })

    return rows


# ──────────────────────────────────────────────────────────────────────────────
# Cookie / browser auth helpers
# ──────────────────────────────────────────────────────────────────────────────

# Map browser forks to their base browser for yt-dlp's cookiesfrombrowser.
_BROWSER_FORK_MAP: dict[str, str] = {
    "floorp": "firefox",
    "librewolf": "firefox",
    "waterfox": "firefox",
    "zen": "firefox",
    "brave": "chrome",
    "vivaldi": "chrome",
    "chromium": "chrome",
}


def _parse_cookies_from_browser(raw: str) -> tuple[str, ...]:
    """Parse a ``browser:profile`` string into a yt-dlp ``cookiesfrombrowser`` tuple.

    Args:
        raw: ``"browser"`` or ``"browser:/path/to/profile"``.

    Returns:
        A tuple compatible with yt-dlp's ``cookiesfrombrowser`` option,
        e.g. ``("firefox",)`` or ``("firefox", "/path", None, None)``.
    """
    value = raw.strip()
    if ":" in value:
        browser_raw, profile = value.split(":", 1)
        browser = _BROWSER_FORK_MAP.get(browser_raw.strip().lower(), browser_raw.strip().lower())
        profile = profile.strip()
        if profile:
            # yt-dlp tuple is (browser, profile, keyring, container); pass None
            # placeholders so absolute paths are never misread as container names.
            return (browser, profile, None, None)
        return (browser,)
    browser = _BROWSER_FORK_MAP.get(value.lower(), value.lower())
    return (browser,)


def _discover_firefox_profiles(browser_hint: str) -> list[str]:
    """Auto-discover Firefox-style browser profiles that have cookies.

    Scans the browser's profile directory for ``profiles.ini`` and
    finds profiles containing ``cookies.sqlite``.

    Args:
        browser_hint: Browser name (floorp, librewolf, firefox, etc.).

    Returns:
        List of absolute profile directory paths.
    """
    home = Path.home()
    hint = browser_hint.strip().lower()
    roots: list[Path] = []
    if hint == "floorp":
        roots.append(home / ".floorp")
    elif hint in {"librewolf"}:
        roots.append(home / ".librewolf")
    elif hint in {"waterfox"}:
        roots.append(home / ".waterfox")
    elif hint in {"zen"}:
        roots.append(home / ".zen")
    else:
        roots.append(home / ".mozilla" / "firefox")

    profiles: list[str] = []
    for root in roots:
        profiles_ini = root / "profiles.ini"
        if profiles_ini.exists():
            try:
                current_section = ""
                values: dict[str, dict[str, str]] = {}
                for raw_line in profiles_ini.read_text(encoding="utf-8").splitlines():
                    line = raw_line.strip()
                    if not line or line.startswith(";"):
                        continue
                    if line.startswith("[") and line.endswith("]"):
                        current_section = line[1:-1].strip()
                        values.setdefault(current_section, {})
                        continue
                    if "=" not in line or not current_section:
                        continue
                    k, v = line.split("=", 1)
                    values.setdefault(current_section, {})[k.strip()] = v.strip()
                for section, cfg in values.items():
                    if not section.lower().startswith("profile"):
                        continue
                    raw_path = cfg.get("Path", "").strip()
                    if not raw_path:
                        continue
                    is_relative = cfg.get("IsRelative", "1").strip() == "1"
                    candidate = (root / raw_path) if is_relative else Path(raw_path)
                    if (candidate / "cookies.sqlite").exists():
                        profiles.append(str(candidate))
            except OSError:
                pass
        if root.exists():
            for cookie_db in root.rglob("cookies.sqlite"):
                candidate = cookie_db.parent
                candidate_str = str(candidate)
                if candidate_str not in profiles:
                    profiles.append(candidate_str)

    unique: list[str] = []
    seen: set[str] = set()
    for p in profiles:
        if p not in seen:
            seen.add(p)
            unique.append(p)
    return unique


def _cookie_browser_candidates(raw: str | None) -> list[tuple[str, ...] | None]:
    """Build a list of ``cookiesfrombrowser`` candidates to try.

    When a browser name is given (e.g. ``"floorp"``), this will try:
    1. The explicit browser spec (e.g. ``("firefox",)``).
    2. Auto-discovered profiles with cookies, if a Firefox fork.

    Args:
        raw: The ``--kuketoj-de-retumilo`` value, or ``None``.

    Returns:
        List of candidate tuples (or ``None`` for no cookies).
    """
    if not raw:
        return [None]
    value = raw.strip()
    if not value:
        return [None]

    base = _parse_cookies_from_browser(value)
    candidates: list[tuple[str, ...] | None] = [base]

    if ":" in value:
        browser_raw = value.split(":", 1)[0].strip().lower()
        mapped = _BROWSER_FORK_MAP.get(browser_raw, browser_raw)
        if mapped == "firefox":
            for profile in _discover_firefox_profiles(browser_raw):
                spec = (mapped, profile, None, None)
                if spec not in candidates:
                    candidates.append(spec)
        if None not in candidates:
            candidates.append(None)
        return candidates

    browser_raw = value.lower()
    mapped = _BROWSER_FORK_MAP.get(browser_raw, browser_raw)
    if mapped == "firefox":
        for profile in _discover_firefox_profiles(browser_raw):
            spec = (mapped, profile, None, None)
            if spec not in candidates:
                candidates.append(spec)
    return candidates


def build_cookie_opts(
    cookies: str | None = None,
    cookies_from_browser: str | None = None,
) -> dict[str, Any]:
    """Build yt-dlp options for cookie authentication.

    Args:
        cookies: Path to a Netscape-format cookies.txt file.
        cookies_from_browser: Browser name or ``"browser:profile"`` string.

    Returns:
        Dict with ``cookiefile`` and/or ``cookiesfrombrowser`` keys,
        or empty dict if neither source is provided.
    """
    opts: dict[str, Any] = {}
    if cookies:
        opts["cookiefile"] = cookies
    if cookies_from_browser:
        opts["cookiesfrombrowser"] = _parse_cookies_from_browser(cookies_from_browser)
    return opts


def _cookie_help_text() -> str:
    """Return detailed help text for cookie setup."""
    home = Path.home()
    return (
        "Kuketoj helpo:\n"
        "  1) Trovu vian retumilan profilon.\n"
        f"     Floorp (Linux): {home}/.floorp/<profilo>\n"
        f"     Firefox (Linux): {home}/.mozilla/firefox/<profilo>\n"
        "     Konsilo: legu profiles.ini por ĝusta profilo-nomo.\n"
        "  2) Testu kun:\n"
        "     --kuketoj-de-retumilo floorp\n"
        "     aŭ --kuketoj-de-retumilo floorp:/plena/vojo/al/profilo\n"
        "     ekz.: --kuketoj-de-retumilo floorp:/home/vi/.floorp/abc.default-default\n"
        "     (la profilo devas enhavi cookies.sqlite)\n"
        "     Noto: filmeto aŭtomate provas plurajn profilojn por firefox/floorp.\n"
        "  3) CLI-kuketoj-eksporto (preferata):\n"
        "     pip install --user yt-dlp\n"
        "     yt-dlp --cookies-from-browser floorp --cookies /tmp/youtube.cookies.txt"
        " --skip-download https://www.youtube.com/watch?v=dQw4w9WgXcQ\n"
        "     aŭ kun specifa profilo:\n"
        "     yt-dlp --cookies-from-browser firefox:/home/vi/.floorp/abc.default-default"
        " --cookies /tmp/youtube.cookies.txt --skip-download https://www.youtube.com/watch?v=dQw4w9WgXcQ\n"
        "     poste uzu: filmeto serci <teksto> --kuketoj /tmp/youtube.cookies.txt\n"
        "  4) Rapida diagnozo (CLI):\n"
        "     ls ~/.floorp\n"
        "     find ~/.floorp -maxdepth 3 -name cookies.sqlite\n"
        "  5) JavaScript-runtime por YouTube (rekomendata):\n"
        "     sudo apt install -y nodejs\n"
        "     (aŭ instalu deno: https://deno.com/)\n"
        "  6) Se la konto uzas apartajn ujojn (containers),\n"
        "     provu retumilan defaŭltan ujon."
    )


# ──────────────────────────────────────────────────────────────────────────────
# Search strategy persistence
# ──────────────────────────────────────────────────────────────────────────────

_SEARCH_STRATEGY_FILE: Path | None = None


def _get_strategy_path() -> Path:
    """Get the path to the search strategy JSON file.

    Creates the parent directory if needed.

    Returns:
        ``<data_dir>/medio/serĉa_strategio.json``
    """
    global _SEARCH_STRATEGY_FILE
    if _SEARCH_STRATEGY_FILE is None:
        path = data_dir() / "medio" / "serĉa_strategio.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        _SEARCH_STRATEGY_FILE = path
    return _SEARCH_STRATEGY_FILE


def _load_search_strategy() -> dict[str, Any]:
    """Load previously saved search strategy from disk.

    Returns:
        Dict with ``"opts"`` key if a strategy was saved, or empty dict.
    """
    path = _get_strategy_path()
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return raw if isinstance(raw, dict) else {}


def _save_search_strategy(strategy: dict[str, Any]) -> None:
    """Persist a working search strategy so future searches try it first.

    Args:
        strategy: Dict with at least ``"opts"`` (yt-dlp options that worked).
    """
    def _json_safe(value: Any) -> Any:
        if value is None or isinstance(value, (bool, int, float, str)):
            return value
        if isinstance(value, tuple):
            return [_json_safe(v) for v in value]
        if isinstance(value, list):
            return [_json_safe(v) for v in value]
        if isinstance(value, set):
            return sorted(_json_safe(v) for v in value)
        if isinstance(value, dict):
            return {str(k): _json_safe(v) for k, v in value.items()}
        return str(value)

    path = _get_strategy_path()
    try:
        path.write_text(
            json.dumps(_json_safe(strategy), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError:
        pass  # Persistence is best-effort


# ──────────────────────────────────────────────────────────────────────────────
# YtDlpWrapper — singleton with lazy import & availability detection
# ──────────────────────────────────────────────────────────────────────────────


class YtDlpWrapper:
    """Singleton wrapper around the yt-dlp Python library.

    Handles lazy import, availability detection, and provides a factory
    method for creating ``YoutubeDL`` context-manager instances.

    Usage::

        wrapper = YtDlpWrapper()
        if wrapper.is_available():
            with wrapper.create_ydl({"quiet": True}) as ydl:
                info = ydl.extract_info(url, download=False)
    """

    _instance: YtDlpWrapper | None = None
    _available: bool | None = None

    def __new__(cls) -> YtDlpWrapper:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    # ── availability ──────────────────────────────────────────────────────

    def is_available(self) -> bool:
        """Check whether yt-dlp is available.

        Checks for the ``yt-dlp`` CLI binary first, then tries importing
        the Python library.  The result is cached.

        Returns:
            True if yt-dlp can be used.
        """
        if self._available is None:
            # Check CLI binary first
            if shutil.which("yt-dlp") is not None:
                self._available = True
            else:
                # Fall back to Python library
                try:
                    import yt_dlp  # type: ignore[import-untyped]  # noqa: F401
                    self._available = True
                except ImportError:
                    self._available = False
        return self._available

    # ── factory ───────────────────────────────────────────────────────────

    @contextmanager
    def create_ydl(self, opts: dict[str, Any] | None = None) -> Generator[YoutubeDL, None, None]:
        """Create a ``YoutubeDL`` instance usable as a context manager.

        Args:
            opts: Options passed to the ``YoutubeDL`` constructor.

        Yields:
            A ``YoutubeDL`` instance.

        Raises:
            RuntimeError: If yt-dlp is not available.
        """
        if not self.is_available():
            raise RuntimeError("yt-dlp is not available")
        ydl = _get_ytdl_class()(opts or {})
        try:
            yield ydl
        finally:
            ydl.close()


# ──────────────────────────────────────────────────────────────────────────────
# YouTube video data structure
# ──────────────────────────────────────────────────────────────────────────────


class YouTubeVideo:
    """YouTube video data."""

    def __init__(
        self,
        video_id: str,
        title: str,
        description: str = "",
        author: str = "",
        duration: int = 0,
        view_count: int = 0,
        upload_date: str = "",
        thumbnail_url: str = "",
        url: str = "",
    ) -> None:
        self.video_id = video_id
        self.title = title
        self.description = description
        self.author = author
        self.duration = duration
        self.view_count = view_count
        self.upload_date = upload_date
        self.thumbnail_url = thumbnail_url
        self.url = url or f"https://www.youtube.com/watch?v={video_id}"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for storage."""
        return {
            "video_id": self.video_id,
            "title": self.title,
            "description": self.description,
            "author": self.author,
            "duration": self.duration,
            "view_count": self.view_count,
            "upload_date": self.upload_date,
            "thumbnail_url": self.thumbnail_url,
            "url": self.url,
        }

    @classmethod
    def from_yt_dlp(cls, data: dict[str, Any]) -> "YouTubeVideo":
        """Create YouTubeVideo from yt-dlp JSON output."""
        return cls(
            video_id=data.get("id", ""),
            title=data.get("title", ""),
            description=data.get("description", ""),
            author=data.get("uploader", ""),
            duration=data.get("duration", 0),
            view_count=data.get("view_count", 0),
            upload_date=data.get("upload_date", ""),
            thumbnail_url=data.get("thumbnail", ""),
            url=data.get("webpage_url", ""),
        )


# ──────────────────────────────────────────────────────────────────────────────
# Batch download result
# ──────────────────────────────────────────────────────────────────────────────


@dataclass
class BatchResult:
    """Result of a single batch-download operation.

    Attributes:
        row: Row number in the input (1-indexed).
        url: The URL that was downloaded.
        success: Whether the download succeeded.
        files: List of paths to downloaded files.
        error: Error message if *success* is False.
    """

    row: int
    url: str
    success: bool
    files: list[Path] = field(default_factory=list)
    error: str | None = None


# ──────────────────────────────────────────────────────────────────────────────
# YouTube service
# ──────────────────────────────────────────────────────────────────────────────


class YouTubeService(MediaService):
    """YouTube media service using yt-dlp."""

    _service: CRUDService | None = None

    def __init__(self) -> None:
        self._wrapper = YtDlpWrapper()

    @classmethod
    def get_service(cls) -> CRUDService:
        """Get or create the CRUDService instance."""
        if cls._service is None:
            db = get_db()
            fts_config = FTSConfig(
                table="youtube_videos",
                fts_columns=["title", "description", "author"],
                filter_columns=["video_id", "author"],
                normalize={
                    "title": fold_search_text,
                    "description": fold_search_text,
                    "author": fold_search_text,
                },
            )
            cls._service = CRUDService(db, "youtube_videos", fts_config=fts_config)
        return cls._service

    def is_available(self) -> bool:
        """Check if yt-dlp is installed."""
        return self._wrapper.is_available()

    def get_download_dir(self) -> str:
        """Return the configured download directory."""
        return get_download_dir()

    # ── search ────────────────────────────────────────────────────────────

    def _yt_dlp_search(
        self,
        query: str,
        limit: int = 10,
        cookies: str | None = None,
        cookies_from_browser: str | None = None,
    ) -> list[YouTubeVideo]:
        """Search YouTube via yt-dlp with retry strategy.

        Builds a queue of candidate option sets (saved strategy first,
        then explicit cookies, then browser profiles, then bare) and tries
        each until one returns results.  On certificate or format errors,
        fallback variants are automatically appended.

        Args:
            query: Search query string.
            limit: Max number of results.
            cookies: Path to a Netscape cookies.txt file.
            cookies_from_browser: Browser name or ``"browser:profile"``.

        Returns:
            List of ``YouTubeVideo`` objects (may be empty).
        """
        if not self.is_available():
            error(tr_multi(
                "yt-dlp ne estas instalita. Instalu ĝin por uzi serĉon.",
                "yt-dlp is not installed. Install it to use search.",
                "yt-dlp n'est pas installé. Installez-le pour utiliser la recherche.",
            ))
            return []

        base_opts: dict[str, Any] = {
            "quiet": True,
            "skip_download": True,
            "no_warnings": True,
            "ignoreerrors": True,
            "extract_flat": False,
        }

        # ── Build candidate queue ─────────────────────────────────────────
        candidates: list[dict[str, Any]] = []

        # 1. Saved strategy (tried first — fastest path)
        cached = _load_search_strategy()
        cached_opts = cached.get("opts")
        if isinstance(cached_opts, dict):
            candidates.append(dict(cached_opts))

        # 2. Explicit cookie file
        if cookies:
            with_cookie = dict(base_opts)
            with_cookie["cookiefile"] = cookies
            candidates.append(with_cookie)

        # 3. Browser cookies (with auto-discovered profiles)
        for browser_spec in _cookie_browser_candidates(cookies_from_browser):
            with_browser = dict(base_opts)
            if browser_spec is not None:
                with_browser["cookiesfrombrowser"] = browser_spec
            candidates.append(with_browser)

        # 4. Fallback: bare opts
        if not candidates:
            candidates.append(dict(base_opts))

        # ── Try candidates with retry ─────────────────────────────────────
        search_query = f"ytsearch{max(1, limit)}:{query}"
        last_error: DownloadError | Exception | None = None
        pending = list(candidates)
        seen: set[str] = set()

        while pending:
            opts = pending.pop(0)
            opts_key = json.dumps(opts, sort_keys=True, default=str)
            if opts_key in seen:
                continue
            seen.add(opts_key)

            try:
                with self._wrapper.create_ydl(opts) as ydl:
                    result = ydl.extract_info(search_query, download=False)
            except _get_download_error() as exc:
                last_error = exc
                msg = str(exc).lower()
                # Certificate error → retry with nocheckcertificate
                if ("certificate_verify_failed" in msg or "hostname mismatch" in msg
                        or "certificateverifyerror" in msg) and not opts.get("nocheckcertificate"):
                    retry = dict(opts)
                    retry["nocheckcertificate"] = True
                    pending.append(retry)
                # Format not available → retry with extract_flat
                if "requested format is not available" in msg and not opts.get("extract_flat"):
                    retry = dict(opts)
                    retry["extract_flat"] = True
                    pending.append(retry)
                continue

            # Filter result entries
            entries = result.get("entries") if isinstance(result, dict) else []
            filtered = [
                e for e in list(entries or [])
                if isinstance(e, dict)
                and str(e.get("availability") or "").lower() not in {
                    "private", "premium_only", "subscriber_only",
                    "needs_auth", "unavailable",
                }
            ]

            if filtered:
                # Save successful strategy
                _save_search_strategy({"opts": opts, "source": "search-success"})
                return [YouTubeVideo.from_yt_dlp(e) for e in filtered]

            # 0 usable entries → add fallback variants
            if not opts.get("nocheckcertificate"):
                retry = dict(opts)
                retry["nocheckcertificate"] = True
                pending.append(retry)
            if not opts.get("extract_flat"):
                retry = dict(opts)
                retry["extract_flat"] = True
                pending.append(retry)

        # All candidates exhausted
        if last_error:
            error(tr_multi(
                f"Serĉo fiaskis: {last_error}",
                f"Search failed: {last_error}",
                f"Échec de recherche: {last_error}",
            ))
        else:
            error(tr_multi(
                "Neniuj rezultoj trovitaj.",
                "No results found.",
                "Aucun résultat trouvé.",
            ))
        return []

    def search(
        self,
        query: str,
        **opts: Any,
    ) -> list[dict[str, Any]]:
        """Search YouTube for videos.

        Args:
            query: Search query string.
            **opts: Additional options:
                - limit: Max results (default 10).
                - cookies: Path to cookies.txt file.
                - cookies_from_browser: Browser name or ``"browser:profile"``.
                - filter: Field to filter on (title, description, author).
                - regex: Regex pattern to match.

        Returns:
            List of video dicts.
        """
        limit = opts.get("limit", 10)
        cookies = opts.get("cookies")
        cookies_from_browser = opts.get("cookies_from_browser")

        videos = self._yt_dlp_search(
            query,
            limit=limit,
            cookies=cookies,
            cookies_from_browser=cookies_from_browser,
        )

        if not videos:
            return []

        # Store in database
        service = self.get_service()
        now = datetime.now().isoformat()
        for video in videos:
            existing = service.get_by_field("video_id", video.video_id)
            if not existing:
                service.create({
                    "video_id": video.video_id,
                    "title": video.title,
                    "description": video.description,
                    "author": video.author,
                    "duration": video.duration,
                    "view_count": video.view_count,
                    "upload_date": video.upload_date,
                    "thumbnail_url": video.thumbnail_url,
                    "url": video.url,
                    "kreita_je": now,
                    "modifita_je": now,
                })

        results = [v.to_dict() for v in videos]

        if "filter" in opts and "regex" in opts:
            field = opts["filter"]
            pattern = opts["regex"]
            results = [r for r in results if self._regex_match(str(r.get(field, "")), pattern)]
        elif "regex" in opts:
            pattern = opts["regex"]
            results = [
                r for r in results
                if self._regex_match(r.get("title", ""), pattern)
                or self._regex_match(r.get("description", ""), pattern)
                or self._regex_match(r.get("author", ""), pattern)
            ]

        return results

    def _regex_match(self, text: str, pattern: str) -> bool:
        """Check if text matches regex pattern (case-insensitive)."""
        try:
            return bool(re.search(pattern, text, re.IGNORECASE))
        except re.error:
            return False

    # ── local cache ──────────────────────────────────────────────────────

    def get_by_id(self, video_id: str) -> dict[str, Any] | None:
        """Get a video by ID from local cache.

        Args:
            video_id: The YouTube video ID.

        Returns:
            Video dict or None.
        """
        service = self.get_service()
        return service.get_by_field("video_id", video_id)

    def search_local(self, query: str, **opts: Any) -> list[dict[str, Any]]:
        """Search local cache only (using FTS5).

        Args:
            query: Search query string.
            **opts: Additional options passed to FTS search.

        Returns:
            List of video dicts from local cache.
        """
        service = self.get_service()
        return service.search_fts(query, **opts)

    # ── download ─────────────────────────────────────────────────────────

    def download(
        self,
        url: str,
        **opts: Any,
    ) -> list[Path]:
        """Download a YouTube video/audio.

        Args:
            url: YouTube URL to download.
            **opts: Download options:
                - output_dir: Output directory (default: from config).
                - resolution: Max video height (e.g. 720, 1080).
                - audio_only: Extract audio only.
                - video_only: Video stream only (no audio).
                - audio_bitrate: Max audio bitrate in kbps.
                - subtitles: Subtitle spec (auto, all, or langs).
                - cookies: Path to cookies.txt file.
                - cookies_from_browser: Browser name or ``"browser:profile"``.

        Returns:
            List of paths to downloaded files (empty if failed).
        """
        if not self.is_available():
            error(tr_multi(
                "yt-dlp ne estas instalita. Instalu ĝin por elŝuti.",
                "yt-dlp is not installed. Install it to download.",
                "yt-dlp n'est pas installé. Installez-le pour télécharger.",
            ))
            return []

        output_dir = Path(opts.get("output_dir", self.get_download_dir()))
        output_dir.mkdir(parents=True, exist_ok=True)

        format_sel = build_format_selector(
            resolution=opts.get("resolution"),
            audio_only=opts.get("audio_only", False),
            video_only=opts.get("video_only", False),
            audio_bitrate=opts.get("audio_bitrate"),
        )

        ydl_opts: dict[str, Any] = {
            "quiet": True,
            "no_warnings": True,
            "format": format_sel,
            "outtmpl": str(output_dir / "%(title).80s [%(id)s].%(ext)s"),
            "ignoreerrors": True,
        }
        ydl_opts.update(build_subtitle_opts(opts.get("subtitles")))
        ydl_opts.update(build_cookie_opts(
            cookies=opts.get("cookies"),
            cookies_from_browser=opts.get("cookies_from_browser"),
        ))

        before = {p for p in output_dir.iterdir()} if output_dir.exists() else set()

        try:
            with self._wrapper.create_ydl(ydl_opts) as ydl:
                ydl.extract_info(url, download=True)
        except _get_download_error() as exc:
            error(tr_multi(
                f"Elŝuto fiaskis: {exc}",
                f"Download failed: {exc}",
                f"Téléchargement échoué: {exc}",
            ))
            return []

        after = {p for p in output_dir.iterdir()}
        created = sorted(after - before, key=lambda p: p.name)

        if created:
            info(tr_multi(
                f"Elŝutis {len(created)} dosiero(j)n al {output_dir}",
                f"Downloaded {len(created)} file(s) to {output_dir}",
                f"Téléchargé {len(created)} fichier(s) vers {output_dir}",
            ))
        else:
            info(tr_multi(
                "Neniu dosiero elŝutita.",
                "No files downloaded.",
                "Aucun fichier téléchargé.",
            ))

        return created

    def batch_download(
        self,
        specs: list[dict[str, Any]],
    ) -> list[BatchResult]:
        """Download multiple items from a list of download specs.

        Each spec should contain at least ``"targets"`` (list of URLs).
        Other keys are forwarded to :meth:`download` as ``**opts``.

        Args:
            specs: List of download-spec dicts (e.g. from :func:`parse_csv_rows`).

        Returns:
            List of :class:`BatchResult` — one per URL across all specs.
        """
        results: list[BatchResult] = []
        row = 0
        for spec in specs:
            targets: list[str] = spec.pop("targets", [])
            if not targets:
                continue
            for url in targets:
                row += 1
                try:
                    files = self.download(url, **spec)
                    results.append(BatchResult(
                        row=row,
                        url=url,
                        success=len(files) > 0,
                        files=files,
                    ))
                except Exception as exc:  # noqa: BLE001
                    results.append(BatchResult(
                        row=row,
                        url=url,
                        success=False,
                        error=str(exc),
                    ))

        return results


# ──────────────────────────────────────────────────────────────────────────────
# Service singleton
# ──────────────────────────────────────────────────────────────────────────────

_service_instance: YouTubeService | None = None


def get_youtube_service() -> YouTubeService:
    """Get the YouTube service singleton.

    Returns:
        The shared ``YouTubeService`` instance.
    """
    global _service_instance
    if _service_instance is None:
        _service_instance = YouTubeService()
    return _service_instance


__all__ = [
    "YouTubeService",
    "YouTubeVideo",
    "YtDlpWrapper",
    "BatchResult",
    "get_youtube_service",
    "build_format_selector",
    "build_subtitle_opts",
    "build_cookie_opts",
    "parse_csv_rows",
    "_cookie_help_text",
]
