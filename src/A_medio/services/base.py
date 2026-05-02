"""Base media service interface."""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any


class MediaService(ABC):
    """Abstract base class for media services."""

    @abstractmethod
    def is_available(self) -> bool:
        """Check if the service is available (e.g., required tool installed).

        Returns:
            True if the underlying tool/backend is available.
        """
        ...

    @abstractmethod
    def search(self, query: str, **opts: Any) -> list[dict[str, Any]]:
        """Search for media items.

        Args:
            query: Search query string.
            **opts: Additional options (filter, regex, etc.).

        Returns:
            List of media items as dicts.
        """
        ...

    @abstractmethod
    def get_by_id(self, media_id: str) -> dict[str, Any] | None:
        """Get a specific media item by ID.

        Args:
            media_id: The unique identifier for the media.

        Returns:
            Media item dict or None if not found.
        """
        ...

    @abstractmethod
    def download(
        self,
        url: str,
        **opts: Any,
    ) -> list[Path]:
        """Download a media item.

        Args:
            url: URL of the media to download.
            **opts: Additional download options:
                - output_dir: Output directory path.
                - resolution: Max height (e.g. 720, 1080).
                - audio_only: Extract audio only.
                - video_only: Video stream only (no audio).
                - subtitles: Subtitle spec (auto, all, or comma-separated langs).

        Returns:
            List of paths to downloaded files.
        """
        ...

    @abstractmethod
    def batch_download(
        self,
        specs: list[dict[str, Any]],
    ) -> list[Any]:
        """Download multiple items from a list of download specs.

        Args:
            specs: List of download-spec dicts, each with at least
                ``"targets"`` (list of URL strings).

        Returns:
            List of result objects (one per URL).
        """
        ...