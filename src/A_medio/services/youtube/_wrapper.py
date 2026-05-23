"""Lazy imports and YtDlpWrapper singleton."""

from __future__ import annotations

from contextlib import contextmanager
from typing import TYPE_CHECKING, Any, Generator

from A import error, info, run, tr_multi

if TYPE_CHECKING:
    from yt_dlp import YoutubeDL
    from yt_dlp.utils import DownloadError


# ── Lazy imports for yt-dlp (avoids import overhead when not used) ──────

_ytdl_class: type[YoutubeDL] | None = None
_download_error_class: type[DownloadError] | None = None


def get_ytdl_class() -> type[YoutubeDL]:
    """Lazy import ``yt_dlp.YoutubeDL``.

    Returns:
        The ``YoutubeDL`` class.

    Raises:
        RuntimeError: If yt-dlp is not available.
    """
    global _ytdl_class
    if _ytdl_class is None:
        try:
            from yt_dlp import YoutubeDL  # type: ignore[import-untyped]

            _ytdl_class = YoutubeDL
        except ImportError as exc:
            raise RuntimeError(
                "yt-dlp is not available. Call ensure_installed() first."
            ) from exc
    return _ytdl_class


def get_download_error() -> type[DownloadError]:
    """Lazy import ``yt_dlp.utils.DownloadError``.

    Returns:
        The ``DownloadError`` exception class.

    Raises:
        RuntimeError: If yt-dlp is not available.
    """
    global _download_error_class
    if _download_error_class is None:
        try:
            from yt_dlp.utils import DownloadError  # type: ignore[import-untyped]

            _download_error_class = DownloadError
        except ImportError as exc:
            raise RuntimeError(
                "yt-dlp is not available. Call ensure_installed() first."
            ) from exc
    return _download_error_class


# ── YtDlpWrapper singleton ──────────────────────────────────────────────


class YtDlpWrapper:
    """Singleton wrapper around the yt-dlp Python library.

    Handles lazy import, availability detection, and provides a factory
    method for creating ``YoutubeDL`` context-manager instances.
    """

    _instance: YtDlpWrapper | None = None
    _available: bool | None = None

    def __new__(cls) -> YtDlpWrapper:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def is_available(self) -> bool:
        """Check whether yt-dlp Python library is available.

        Tries importing ``yt_dlp.YoutubeDL`` — the result is cached.

        Returns:
            True if ``yt_dlp`` can be imported and used.
        """
        if self._available is None:
            try:
                from yt_dlp import YoutubeDL  # type: ignore[import-untyped]

                _ = YoutubeDL
                self._available = True
            except ImportError:
                self._available = False
        return self._available

    def ensure_installed(self) -> bool:
        """Ensure yt-dlp is installed, prompting the user if missing.

        Returns:
            True if yt-dlp is available (was already or became so).
        """
        if self.is_available():
            return True

        import sys
        import typer

        answer = typer.prompt(
            tr_multi(
                "yt-dlp ne estas instalita. Cu instali ghin? (j/N)",
                "yt-dlp is not installed. Install it? (y/N)",
                "yt-dlp n'est pas installe. L'installer ? (o/N)",
            ),
            default="n",
        )
        if answer.strip().lower() not in {"j", "jes", "y", "yes"}:
            return False

        info(
            tr_multi(
                "Instalante yt-dlp...",
                "Installing yt-dlp...",
                "Installation de yt-dlp...",
            )
        )
        result = run(sys.executable, "-m", "pip", "install", "yt-dlp", timeout=120)
        if result.returncode == 0:
            self._available = None  # reset cache
            return self.is_available()

        error(
            tr_multi(
                "Malsukcesis instali yt-dlp. Instalu permane: pip install yt-dlp",
                "Failed to install yt-dlp. Install manually: pip install yt-dlp",
                "Echec de l'installation de yt-dlp. Installez manuellement : pip install yt-dlp",
            )
        )
        return False

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
        ydl = get_ytdl_class()(opts or {})
        try:
            yield ydl
        finally:
            ydl.close()
