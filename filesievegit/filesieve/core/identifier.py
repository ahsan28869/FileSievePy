"""MIME type identification with graceful fallbacks."""
from __future__ import annotations

import mimetypes
from pathlib import Path

try:
    import magic  # type: ignore

    _HAS_MAGIC = True
except Exception:  # pragma: no cover - magic may not be installed
    magic = None
    _HAS_MAGIC = False


# Ensure mimetypes has a solid baseline
mimetypes.init()


def detect_mime(path: Path) -> str:
    """Best-effort MIME type detection."""
    if _HAS_MAGIC:
        try:
            mime = magic.Magic(mime=True)
            result = mime.from_file(str(path))
            if result:
                return result
        except Exception:
            pass

    guessed, _ = mimetypes.guess_type(str(path))
    if guessed:
        return guessed

    return "application/octet-stream"


def mime_matches(mime: str, patterns: list[str]) -> bool:
    """Return True if `mime` matches any of the given patterns.

    Supports exact matches and wildcards like ``image/*``.
    """
    if not patterns:
        return False
    mime_lower = mime.lower()
    for pattern in patterns:
        pattern_lower = pattern.lower()
        if pattern_lower.endswith("/*"):
            prefix = pattern_lower[:-1]  # keep the slash
            if mime_lower.startswith(prefix):
                return True
        elif pattern_lower.endswith("*"):
            if mime_lower.startswith(pattern_lower[:-1]):
                return True
        elif mime_lower == pattern_lower:
            return True
    return False