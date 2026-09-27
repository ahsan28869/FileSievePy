"""Safe filesystem primitives: atomic moves, collision-safe claims, sanitization."""
from __future__ import annotations

import errno
import hashlib
import os
import re
import shutil
import sys
import time
import unicodedata
from pathlib import Path
from typing import Optional

from filesieve.utils.logger import get_logger


logger = get_logger(__name__)

IS_WINDOWS = sys.platform == "win32"

# Windows reserved device names — case-insensitive, no extension needed.
_WINDOWS_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}

# Characters never allowed in a path component on any supported OS.
_INVALID_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

# Extensions that indicate a file is still being written.
TEMP_EXTENSIONS = {
    ".tmp", ".temp", ".part", ".partial", ".crdownload", ".download",
    ".opdownload", ".swp", ".swx", ".lock", ".~lock", ".!ut", ".aria2",
}

TEMP_PREFIXES = ("~$", ".~", "~")


# ---------------------------------------------------------------------- #
# Sanitization
# ---------------------------------------------------------------------- #
def sanitize_component(name: str, replacement: str = "_") -> str:
    """Sanitize a single path component (no separators, no reserved names)."""
    if not name:
        return "unnamed"

    # Normalize Unicode to NFC for consistent comparison
    name = unicodedata.normalize("NFC", name)

    # Strip any directory separators — a single component cannot contain them
    name = name.replace("/", replacement).replace("\\", replacement)

    # Remove control characters and other invalid chars
    name = _INVALID_CHARS.sub(replacement, name)

    # Windows: strip trailing dots and spaces (illegal, and Explorer strips them)
    name = name.rstrip(" .")

    if not name:
        name = "unnamed"

    # Windows reserved names — check the stem, not the whole name
    stem = name.split(".")[0].upper()
    if IS_WINDOWS and stem in _WINDOWS_RESERVED:
        name = f"_{name}"

    # Keep it reasonable
    if len(name) > 200:
        dot = name.rfind(".")
        if dot > 0 and len(name) - dot <= 10:
            ext = name[dot:]
            name = name[: 200 - len(ext)] + ext
        else:
            name = name[:200]

    return name


def is_temp_file(path: Path) -> bool:
    """Return True if the path looks like an in-progress / temp file."""
    name = path.name
    if path.suffix.lower() in TEMP_EXTENSIONS:
        return True
    for prefix in TEMP_PREFIXES:
        if name.startswith(prefix):
            return True
    if name.endswith((".crdownload", ".part", ".download")):
        return True
    return False


# ---------------------------------------------------------------------- #
# Windows long-path handling
# ---------------------------------------------------------------------- #
def extended_path(path: Path) -> str:
    """Return a Windows extended-length path if needed, else the plain str."""
    p = str(path)
    if IS_WINDOWS and len(p) > 240 and not p.startswith("\\\\?\\"):
        if p.startswith("\\\\"):  # UNC
            return "\\\\?\\UNC\\" + p[2:]
        return "\\\\?\\" + p
    return p


# ---------------------------------------------------------------------- #
# Path containment (defense against traversal)
# ---------------------------------------------------------------------- #
def is_inside(child: Path, parent: Path) -> bool:
    """Return True if `child` is inside `parent` (after resolving symlinks)."""
    try:
        child_r = child.resolve(strict=False)
        parent_r = parent.resolve(strict=False)
    except OSError:
        return False

    try:
        child_r.relative_to(parent_r)
        return True
    except ValueError:
        return False


def assert_inside(child: Path, parent: Path) -> Path:
    """Raise ValueError if `child` is not inside `parent`. Returns resolved child."""
    if not is_inside(child, parent):
        raise ValueError(f"Refusing path outside root: {child} not inside {parent}")
    return child.resolve(strict=False)


# ---------------------------------------------------------------------- #
# Settle check — don't touch files still being written
# ---------------------------------------------------------------------- #
def file_is_stable(
    path: Path,
    settle_seconds: float = 0.5,
    required_checks: int = 3,
    timeout: float = 30.0,
) -> bool:
    """Return True when a file's size hasn't changed across several polls
    AND we can acquire an exclusive lock on it (or open it for read+write)."""
    deadline = time.monotonic() + timeout
    last_size = -1
    stable_count = 0

    while time.monotonic() < deadline:
        if not path.exists():
            return False

        try:
            size = path.stat().st_size
        except OSError:
            return False

        if size == last_size and size > 0:
            stable_count += 1
            if stable_count >= required_checks:
                return _can_lock(path)
        else:
            stable_count = 0
            last_size = size

        time.sleep(settle_seconds)

    return False


def _can_lock(path: Path) -> bool:
    """Best-effort check that the file is not open by another process."""
    try:
        fd = os.open(extended_path(path), os.O_RDWR)
        try:
            pass
        finally:
            os.close(fd)
        return True
    except OSError as exc:
        # Windows sharing violation = still being written
        if exc.errno in (errno.EACCES, errno.EBUSY, 13, 32):
            return False
        # Can't open RW but it exists and is readable → probably fine
        try:
            with open(extended_path(path), "rb"):
                return True
        except OSError:
            return False


# ---------------------------------------------------------------------- #
# Collision-safe destination claiming
# ---------------------------------------------------------------------- #
def atomic_claim_path(destination: Path, max_attempts: int = 1000) -> Path:
    """Atomically reserve a unique destination path.

    Uses O_CREAT | O_EXCL to avoid the classic TOCTOU race where two
    events both see the name free and one clobbers the other.
    """
    destination = Path(destination)
    parent = destination.parent
    parent.mkdir(parents=True, exist_ok=True)

    stem = destination.stem
    suffix = destination.suffix

    for i in range(max_attempts):
        if i == 0:
            candidate = destination
        else:
            candidate = parent / f"{stem}_{i}{suffix}"

        try:
            fd = os.open(extended_path(candidate), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
            os.close(fd)
            return candidate
        except FileExistsError:
            continue
        except OSError as exc:
            # Fall back to a UUID-based name for pathological cases
            logger.warning("Atomic claim failed on %s: %s", candidate, exc)
            break

    # Last resort: append a timestamp + short uuid
    import uuid
    fallback = parent / f"{stem}_{int(time.time())}_{uuid.uuid4().hex[:6]}{suffix}"
    fd = os.open(extended_path(fallback), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
    os.close(fd)
    return fallback


# ---------------------------------------------------------------------- #
# Atomic cross-device move with verification
# ---------------------------------------------------------------------- #
def _hash_file(path: Path, chunk: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with open(extended_path(path), "rb") as f:
        while True:
            data = f.read(chunk)
            if not data:
                break
            h.update(data)
    return h.hexdigest()


def _same_filesystem(a: Path, b: Path) -> bool:
    try:
        return os.stat(extended_path(a)).st_dev == os.stat(extended_path(b.parent)).st_dev
    except OSError:
        return False


def safe_move(
    source: Path,
    destination: Path,
    verify_hash: bool = False,
    size_threshold_for_hash: int = 64 * 1024 * 1024,
) -> Path:
    """Move a file with crash-safety.

    - Same filesystem: os.replace (atomic).
    - Cross-device: copy → fsync → verify size (+ hash for large files) → unlink source.
    - Never deletes source until destination is verified.
    """
    source = Path(source)
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)

    if _same_filesystem(source, destination):
        # Atomic rename — safe on the same filesystem
        os.replace(extended_path(source), extended_path(destination))
        return destination

    # Cross-device — do the careful dance
    src_size = source.stat().st_size
    temp_dest = destination.with_name(destination.name + ".filesieve.part")

    try:
        # Copy to a .part file first so a partial never looks complete
        with open(extended_path(source), "rb") as fin, open(extended_path(temp_dest), "wb") as fout:
            shutil.copyfileobj(fin, fout, length=1024 * 1024)
            fout.flush()
            os.fsync(fout.fileno())

        # Verify size
        dst_size = temp_dest.stat().st_size
        if dst_size != src_size:
            raise IOError(f"Size mismatch after copy: {src_size} → {dst_size}")

        # Verify hash for large files (or when explicitly requested)
        if verify_hash or src_size >= size_threshold_for_hash:
            if _hash_file(source) != _hash_file(temp_dest):
                raise IOError("Hash mismatch after copy")

        # Atomic rename into place
        os.replace(extended_path(temp_dest), extended_path(destination))

        # Only now remove the source
        os.unlink(extended_path(source))
        return destination

    except Exception:
        # Clean up partial destination — source is untouched
        try:
            if temp_dest.exists():
                temp_dest.unlink()
        except OSError:
            pass
        raise