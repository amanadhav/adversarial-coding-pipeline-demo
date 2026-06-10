"""File loading with size guard and well-formedness check."""
from __future__ import annotations

import json
import os

DEFAULT_MAX_BYTES = int(os.environ.get("JSON_VALIDATOR_MAX_BYTES", 10 * 1024 * 1024))  # 10 MB default


class LoadError(Exception):
    """Base class for all load-time errors."""


class SizeError(LoadError):
    """File exceeds the allowed size limit."""


class JSONParseError(LoadError):
    """File content is not valid JSON."""


def load_json(path: str, max_bytes: int = DEFAULT_MAX_BYTES) -> object:
    """
    Load and parse a JSON file.

    Parameters
    ----------
    path:
        Absolute or relative path to the JSON file.
    max_bytes:
        Maximum allowed file size in bytes (default 10 MB).

    Returns
    -------
    object
        Parsed JSON value (dict, list, str, int, float, bool, or None).

    Raises
    ------
    LoadError
        For file-not-found or unicode errors.
    JSONParseError
        For malformed JSON.
    SizeError
        When the file exceeds *max_bytes*.
    """
    try:
        with open(path, encoding="utf-8") as fh:
            # Measure size atomically with the open — eliminates TOCTOU race
            fh.seek(0, 2)   # seek to end
            size = fh.tell()
            if size > max_bytes:
                raise SizeError(
                    f"File too large: {path!r} ({size} bytes, max {max_bytes})"
                )
            fh.seek(0)      # seek back to start
            content = fh.read()
    except FileNotFoundError:
        raise LoadError(f"File not found: {path!r}")
    except UnicodeDecodeError as exc:
        raise LoadError(f"Cannot decode file as UTF-8: {path!r}") from exc

    try:
        return json.loads(content)
    except json.JSONDecodeError as exc:
        raise JSONParseError(f"Malformed JSON in {path!r}: {exc}") from exc
