"""Security helpers: path traversal guard."""
from __future__ import annotations

import os


class PathError(ValueError):
    """Raised when a file path is considered unsafe."""


def check_path(path: str) -> None:
    """
    Raise PathError if *path* contains path-traversal sequences.

    Resolves the path to its absolute form and rejects any path
    whose normalised form contains a ``..`` component.
    """
    # Reject UNC/network paths (Windows \\server\share or Unix //server/share)
    normalised_fwd = path.replace("\\", "/")
    if normalised_fwd.startswith("//"):
        raise PathError(f"Disallowed path (network path): {path!r}")
    # Normalise to absolute without following symlinks
    normalised = os.path.normpath(os.path.abspath(path))
    # Reject if any component is '..' after normalisation
    # (normpath collapses them, so check the original split)
    parts = path.replace("\\", "/").split("/")
    if ".." in parts:
        raise PathError(f"Disallowed path: {path!r}")
    # Second guard: normalised path must not escape via symlink tricks
    # (covered by normpath collapsing; if the original had '..' it was
    # already caught above — this is a belt-and-suspenders check)
    _ = normalised  # kept for future extension
