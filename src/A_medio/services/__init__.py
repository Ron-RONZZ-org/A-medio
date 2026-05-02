"""Media services for A-medio."""

from A_medio.services.base import MediaService
from A_medio.services.youtube import YouTubeService

__all__ = ["MediaService", "YouTubeService"]