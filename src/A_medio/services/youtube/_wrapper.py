"""Lazy imports and YtDlpWrapper singleton."""

from __future__ import annotations

from contextlib import contextmanager
from typing import TYPE_CHECKING, Any, Generator

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


# ── Null logger to suppress yt-dlp stderr noise ─────────────────────────


class _NullLogger:
    """Logger that swallows all yt-dlp output.

    yt-dlp prints ``ERROR:`` messages to stderr even with ``quiet=True``.
    We handle errors ourselves via ``DownloadError`` exceptions, so this
    logger prevents duplicate noise reaching the user.
    """

    def debug(self, msg: str) -> None:  # noqa: ARG002
        pass

    def info(self, msg: str) -> None:  # noqa: ARG002
        pass

    def warning(self, msg: str) -> None:  # noqa: ARG002
        pass

    def error(self, msg: str) -> None:  # noqa: ARG002
        pass


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

        Uses :func:`A.utils.deps.ensure_dependency` for standardized
        interactive install with ``uv``-first priority.

        Returns:
            True if yt-dlp is available (was already or became so).
        """
        if self.is_available():
            return True

        from A.utils.deps import ensure_dependency

        try:
            ensure_dependency("yt_dlp", "yt-dlp", timeout=120)
            self._available = None  # reset cache
            return self.is_available()
        except ImportError:
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
        final_opts = dict(opts or {})
        final_opts.setdefault("logger", _NullLogger())
        ydl = get_ytdl_class()(final_opts)
        try:
            yield ydl
        finally:
            ydl.close()
