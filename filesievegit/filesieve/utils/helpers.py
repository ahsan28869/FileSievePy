"""Helper utilities."""
import re
from datetime import datetime
from pathlib import Path


_INVALID_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def sanitize_filename(name: str, replacement: str = "_") -> str:
    """Sanitize a filename by removing invalid characters."""
    cleaned = _INVALID_CHARS.sub(replacement, name)
    cleaned = cleaned.strip(" .")
    if not cleaned:
        cleaned = "unnamed"
    return cleaned[:200]


def ensure_unique_path(path: Path) -> Path:
    """Ensure a path is unique by appending a counter if it exists."""
    if not path.exists():
        return path

    stem = path.stem
    suffix = path.suffix
    parent = path.parent
    counter = 1

    while True:
        candidate = parent / f"{stem}_{counter}{suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def format_size(size_bytes: int) -> str:
    """Format a byte count into a human-readable string."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    for unit in ["KB", "MB", "GB", "TB"]:
        size_bytes /= 1024.0
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
    return f"{size_bytes:.1f} PB"


def format_timestamp(ts: float) -> str:
    """Format a POSIX timestamp into a readable string."""
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")