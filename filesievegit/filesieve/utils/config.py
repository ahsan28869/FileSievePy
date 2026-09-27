"""Configuration management with atomic writes and secure permissions."""
from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

import yaml


CONFIG_DIR = Path(os.environ.get("FILESIEVE_HOME", Path.home() / ".filesieve"))
CONFIG_FILE = CONFIG_DIR / "config.yaml"

SCHEMA_VERSION = 1


DEFAULT_CONFIG: dict[str, Any] = {
    "schema_version": SCHEMA_VERSION,
    "watched_directories": [],
    "output_directory": str(Path.home() / "FileSieve_Archive"),
    "monitoring_enabled": False,
    "recursive": False,
    "rules_file": str(CONFIG_DIR / "rules.yaml"),
    "locations_file": str(CONFIG_DIR / "locations.yaml"),
}


def secure_mkdir(path: Path, mode: int = 0o700) -> None:
    """Create a directory with restrictive permissions (best-effort)."""
    try:
        path.mkdir(parents=True, exist_ok=True)
        if os.name != "nt":
            os.chmod(path, mode)
    except OSError:
        pass


def _atomic_write(path: Path, data: str, mode: int = 0o600) -> None:
    """Write atomically: temp file → fsync → os.replace."""
    secure_mkdir(path.parent)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        if os.name != "nt":
            os.chmod(tmp_name, mode)
        os.replace(tmp_name, path)
        if os.name != "nt":
            os.chmod(path, mode)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def _migrate(data: dict[str, Any]) -> dict[str, Any]:
    """Bring forward older config versions. Currently a no-op but
    the hook is here so future versions can migrate safely."""
    version = int(data.get("schema_version", 0) or 0)
    if version < SCHEMA_VERSION:
        data["schema_version"] = SCHEMA_VERSION
    return data


def load_config() -> dict[str, Any]:
    secure_mkdir(CONFIG_DIR)
    if not CONFIG_FILE.exists():
        save_config(DEFAULT_CONFIG)
        return dict(DEFAULT_CONFIG)

    # Back up before loading, so a bad edit is recoverable
    try:
        shutil.copy2(CONFIG_FILE, CONFIG_FILE.with_suffix(".yaml.bak"))
    except OSError:
        pass

    try:
        with CONFIG_FILE.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except (OSError, yaml.YAMLError):
        data = {}

    if not isinstance(data, dict):
        data = {}

    data = _migrate(data)
    merged = dict(DEFAULT_CONFIG)
    merged.update(data)
    return merged


def save_config(config: dict[str, Any]) -> None:
    try:
        data = yaml.safe_dump(
            config, default_flow_style=False, sort_keys=False, allow_unicode=True
        )
        _atomic_write(CONFIG_FILE, data, mode=0o600)
    except OSError:
        pass


# ---------------------------------------------------------------------- #
# Path cycle detection — used by the UI before saving destinations
# ---------------------------------------------------------------------- #
def is_destination_inside_watched(destination: Path, watched: list[Path]) -> bool:
    """Return True if the destination sits inside any watched root."""
    try:
        dest_r = destination.resolve(strict=False)
    except OSError:
        return False
    for w in watched:
        try:
            w_r = w.resolve(strict=False)
            dest_r.relative_to(w_r)
            return True
        except (OSError, ValueError):
            continue
    return False