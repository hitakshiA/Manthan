"""File-level validation for Bronze-stage ingestion.

These checks run before any loader touches a file. They catch the obvious
failure modes — missing file, directory instead of file, zero-byte file,
oversized upload — and raise :class:`IngestionError` with a clear message
the API layer can surface to the user.
"""

from __future__ import annotations

from pathlib import Path

from src.core.exceptions import IngestionError

_BYTES_PER_MB = 1024 * 1024


def validate_file(path: Path, *, max_size_mb: int) -> None:
    """Validate that ``path`` is a readable, non-empty file within size limits.

    Args:
        path: Path to the candidate input file.
        max_size_mb: Maximum allowed file size in megabytes. Sourced from
            :attr:`src.core.config.Settings.max_upload_size_mb`.

    Raises:
        IngestionError: If the file does not exist, is not a regular file,
            is zero bytes, or exceeds ``max_size_mb``.
    """
    if not path.exists():
        raise IngestionError(f"File does not exist: {path}")
    if not path.is_file():
        raise IngestionError(f"Path is not a regular file: {path}")

    size_bytes = path.stat().st_size
    if size_bytes == 0:
        raise IngestionError(f"File is empty: {path}")

    size_mb = size_bytes / _BYTES_PER_MB
    if size_mb > max_size_mb:
        raise IngestionError(
            f"File {path.name} ({size_mb:.1f} MB) exceeds the "
            f"configured upload limit of {max_size_mb} MB"
        )
