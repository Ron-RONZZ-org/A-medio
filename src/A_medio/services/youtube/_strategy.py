"""Search strategy persistence for yt-dlp search."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from A.core.paths import data_dir

_SEARCH_STRATEGY_FILE: Path | None = None


def _get_strategy_path() -> Path:
    """Get the path to the search strategy JSON file.

    Creates the parent directory if needed.

    Returns:
        ``<data_dir>/medio/serca_strategio.json``
    """
    global _SEARCH_STRATEGY_FILE
    if _SEARCH_STRATEGY_FILE is None:
        path = data_dir() / "medio" / "serca_strategio.json"
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
