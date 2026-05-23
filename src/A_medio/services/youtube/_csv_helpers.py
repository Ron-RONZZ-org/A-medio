"""CSV batch download support for YouTube downloads."""

from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Any

# Mapping of CSV column headers to internal option keys.
_CSV_HEADER_MAP: dict[str, str] = {
    "celoj": "targets",
    "targets": "targets",
    "target": "targets",
    "url": "targets",
    "urls": "targets",
    "difino": "resolution",
    "rezolucio": "resolution",
    "resolution": "resolution",
    "sonkvalito": "audio_bitrate",
    "audio_bitrate": "audio_bitrate",
    "bitrate": "audio_bitrate",
    "audio": "audio_only",
    "filmeto": "video_only",
    "video_only": "video_only",
    "vojo": "output_dir",
    "output_dir": "output_dir",
    "output": "output_dir",
    "path": "output_dir",
    "directory": "output_dir",
    "subtitoloj": "subtitles",
    "subtitles": "subtitles",
    "subs": "subtitles",
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
        f"Uzu jes/ne au true/false."
    )


def parse_csv_rows(
    csv_path: str | Path,
    initial_state: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Parse a CSV file into a list of download specs.

    The CSV **must** have a ``celoj`` (targets) column. Each row
    specifies download options; empty cells inherit from the previous
    row (or from *initial_state* for the first row).

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
                    targets = [t for t in re.split(r"[\s,;]+", cell) if t]
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
