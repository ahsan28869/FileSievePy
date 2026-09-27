"""User-defined per-extension destination mapping."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field, field_validator

from filesieve.core.rules import Rule
from filesieve.utils.config import CONFIG_DIR
from filesieve.utils.logger import get_logger


logger = get_logger(__name__)

LOCATIONS_FILE = CONFIG_DIR / "locations.yaml"


class LocationEntry(BaseModel):
    """A single extension → destination mapping."""

    extension: str = Field(..., description="File extension including the dot, e.g. '.mp4'")
    destination: str = Field(..., description="Absolute folder path to send matching files to")
    enabled: bool = Field(default=True)
    organize_by_date: bool = Field(
        default=False,
        description="If true, appends /{year}/{month} to the destination",
    )

    @field_validator("extension")
    @classmethod
    def _normalize_ext(cls, v: str) -> str:
        v = v.strip().lower()
        if not v:
            raise ValueError("Extension cannot be empty")
        if not v.startswith("."):
            v = "." + v
        return v


class LocationMap(BaseModel):
    """The full collection of user-defined location entries."""

    route_by_type_first: bool = Field(
        default=True,
        description="If true, per-type rules take priority over general rules",
    )
    entries: list[LocationEntry] = Field(default_factory=list)

    def to_rules(self, base_priority: int = 500) -> list[Rule]:
        """Convert every enabled entry into a Rule for the router."""
        rules: list[Rule] = []
        for idx, entry in enumerate(self.entries):
            if not entry.enabled:
                continue

            dest = Path(entry.destination)
            # If the destination is absolute, we need to bypass the archive root.
            # We encode this using the special token below; the router resolves it.
            destination_str = f"__ABS__{dest.as_posix()}"
            if entry.organize_by_date:
                destination_str += "/{year}/{month}"

            rules.append(
                Rule(
                    name=f"Type: {entry.extension}",
                    priority=base_priority - idx,
                    extensions=[entry.extension],
                    destination=destination_str,
                    organize_by_date=False,  # handled inline above
                )
            )
        return rules


# ------------------------------------------------------------------ #
# Persistence
# ------------------------------------------------------------------ #
def load_location_map() -> LocationMap:
    """Load the location map from disk, creating defaults if missing."""
    if not LOCATIONS_FILE.exists():
        empty = LocationMap()
        save_location_map(empty)
        return empty

    try:
        with LOCATIONS_FILE.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return LocationMap(**data)
    except Exception as exc:
        logger.error("Failed to load locations.yaml: %s", exc)
        return LocationMap()


def save_location_map(location_map: LocationMap) -> None:
    """Persist the location map to disk."""
    try:
        with LOCATIONS_FILE.open("w", encoding="utf-8") as f:
            yaml.safe_dump(
                location_map.model_dump(),
                f,
                default_flow_style=False,
                sort_keys=False,
            )
    except OSError as exc:
        logger.error("Failed to save locations.yaml: %s", exc)