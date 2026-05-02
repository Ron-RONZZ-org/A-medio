"""Base media service interface."""

from abc import ABC, abstractmethod
from typing import Any


class MediaService(ABC):
    """Abstract base class for media services."""

    @abstractmethod
    def is_available(self) -> bool:
        """Check if the service is available (e.g., required tool installed)."""
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