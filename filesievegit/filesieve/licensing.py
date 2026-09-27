"""Gumroad license verification + 14-day trial management."""
from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path

import requests

from filesieve.utils.config import CONFIG_DIR, secure_mkdir
from filesieve.utils.logger import get_logger


logger = get_logger(__name__)

TRIAL_FILE = CONFIG_DIR / "trial.json"
LICENSE_FILE = CONFIG_DIR / "license.json"

# ⚠️ Replace with your own Gumroad product_id
GUMROAD_PRODUCT_ID = "your-gumroad-product-id-here"

TRIAL_DAYS = 14


def _machine_id() -> str:
    """Stable per-machine identifier (hashed, not raw)."""
    try:
        import uuid
        raw = f"{uuid.getnode()}-{os.environ.get('COMPUTERNAME', '')}"
    except Exception:
        raw = f"{os.environ.get('USERNAME', '')}-fallback"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def _write_json(path: Path, data: dict) -> None:
    secure_mkdir(path.parent)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


# ---------------------------------------------------------------------- #
# License check
# ---------------------------------------------------------------------- #
def is_licensed() -> bool:
    """Check stored license file. Verifies with Gumroad if online."""
    data = _read_json(LICENSE_FILE)
    key = data.get("license_key")
    if not key:
        return False

    try:
        return _verify_with_gumroad(key)
    except requests.RequestException:
        # Offline: trust the last known-good state
        return data.get("verified", False)


def _verify_with_gumroad(license_key: str) -> bool:
    """Call Gumroad's verify endpoint."""
    try:
        resp = requests.post(
            "https://api.gumroad.com/v2/licenses/verify",
            data={
                "product_id": GUMROAD_PRODUCT_ID,
                "license_key": license_key,
                "increment_uses_count": "false",
            },
            timeout=10,
        )
    except requests.RequestException:
        raise

    if resp.status_code != 200:
        return False

    try:
        body = resp.json()
    except Exception:
        return False

    if not body.get("success"):
        return False

    purchase = body.get("purchase", {})
    if purchase.get("refunded") or purchase.get("chargebacked"):
        return False

    _write_json(LICENSE_FILE, {
        "license_key": license_key,
        "email": purchase.get("email", ""),
        "verified": True,
        "verified_at": time.time(),
    })
    return True


def activate_license(license_key: str) -> tuple[bool, str]:
    """Called from GUI. Returns (success, message)."""
    key = license_key.strip().upper()
    if not key or len(key) < 20:
        return False, "Please enter a valid license key."

    try:
        ok = _verify_with_gumroad(key)
    except requests.RequestException as exc:
        logger.error("License verification failed: %s", exc)
        return False, "Cannot reach Gumroad. Check your internet connection."

    if ok:
        return True, "License activated. Thank you!"
    return False, "Invalid or expired license key."


# ---------------------------------------------------------------------- #
# Trial check
# ---------------------------------------------------------------------- #
def trial_status() -> dict:
    """Return {'state': 'new'|'active'|'expired', 'days_left': int}."""
    data = _read_json(TRIAL_FILE)
    now = time.time()

    if "started_at" not in data:
        return {"state": "new", "days_left": TRIAL_DAYS}

    started = data["started_at"]
    elapsed_days = (now - started) / 86400.0
    days_left = max(0, TRIAL_DAYS - int(elapsed_days))

    if days_left <= 0:
        return {"state": "expired", "days_left": 0}
    return {"state": "active", "days_left": days_left}


def start_trial() -> None:
    """Record the trial start time (only if not already started)."""
    data = _read_json(TRIAL_FILE)
    if "started_at" not in data:
        data["started_at"] = time.time()
        data["machine_id"] = _machine_id()
        _write_json(TRIAL_FILE, data)


def has_access() -> bool:
    """True if the app should unlock (licensed or trial active)."""
    if is_licensed():
        return True
    status = trial_status()
    return status["state"] == "active"