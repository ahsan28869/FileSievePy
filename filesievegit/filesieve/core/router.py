"""Router with crash-safe moves, atomic collisions, and journal integration."""

from __future__ import annotations

import re
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from filesieve.core.identifier import detect_mime, mime_matches
from filesieve.core.rules import Rule, RuleSet
from filesieve.utils.journal import Journal
from filesieve.utils.logger import get_logger
from filesieve.utils.safe_io import (
    assert_inside,
    atomic_claim_path,
    is_inside,
    safe_move,
    sanitize_component,
)

logger = get_logger(__name__)


class RouteResult:
    """Outcome of routing a single file."""

    def __init__(
        self,
        source: Path,
        destination: Optional[Path],
        rule_name: Optional[str],
        success: bool,
        error: Optional[str] = None,
        dry_run: bool = False,
    ) -> None:
        self.source = source
        self.destination = destination
        self.rule_name = rule_name
        self.success = success
        self.error = error
        self.dry_run = dry_run

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"RouteResult(source={self.source!r}, destination={self.destination!r}, "
            f"rule={self.rule_name!r}, success={self.success}, error={self.error!r}, "
            f"dry_run={self.dry_run})"
        )


class FileRouter:
    """Routes files into structured directory hierarchies securely and safely."""

    def __init__(
        self,
        ruleset: RuleSet,
        output_directory: Path,
        dry_run: bool = False,
        journal: Optional[Journal] = None,
    ) -> None:
        self.ruleset = ruleset
        self.output_directory = Path(output_directory).resolve(strict=False)
        self.dry_run = dry_run
        self.journal = journal

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def route(self, file_path: Path) -> RouteResult:
        """Route a single file according to rules with collision checking and journaling."""
        file_path = Path(file_path)

        if not file_path.exists() or not file_path.is_file():
            return RouteResult(file_path, None, None, False, "File does not exist")

        try:
            mime = detect_mime(file_path)
            stat = file_path.stat()
        except OSError as exc:
            return RouteResult(file_path, None, None, False, str(exc))

        matched = self._match_rule(file_path, mime, stat.st_size)
        if matched is None:
            return RouteResult(file_path, None, None, False, "No matching rule")

        # -------- Absolute vs. archive-root destinations ------------- #
        try:
            target_root, rel = self._resolve_root_and_rel(matched, file_path)
        except ValueError as exc:
            return RouteResult(file_path, None, matched.name, False, str(exc))

        # -------- Cycle check: destination must not be watched ------ #
        if is_inside(target_root, file_path.parent):
            # Destination inside the watched folder — would loop. Skip.
            return RouteResult(
                file_path,
                None,
                matched.name,
                False,
                "Destination is inside a watched folder (would loop)",
            )

        # -------- Atomic collision-safe destination claim ----------- #
        try:
            final_dest = atomic_claim_path(rel)
            assert_inside(final_dest, target_root)
        except Exception as exc:
            return RouteResult(
                file_path, None, matched.name, False, f"Destination error: {exc}"
            )

        if self.dry_run:
            return RouteResult(
                file_path, final_dest, matched.name, True, dry_run=True
            )

        # -------- Journal + move ------------------------------------ #
        move_id: Optional[int] = None
        if self.journal is not None:
            move_id = self.journal.begin_move(file_path, final_dest, matched.name)

        try:
            safe_move(file_path, final_dest)
            if self.journal is not None and move_id:
                self.journal.complete_move(move_id)
            logger.info(
                "Routed %s -> %s (rule: %s)",
                file_path.name,
                final_dest,
                matched.name,
            )
            return RouteResult(file_path, final_dest, matched.name, True)
        except Exception as exc:
            if self.journal is not None and move_id:
                self.journal.fail_move(move_id, str(exc))
            logger.error("Move failed %s -> %s: %s", file_path, final_dest, exc)
            return RouteResult(file_path, final_dest, matched.name, False, str(exc))

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #
    def _match_rule(self, file_path: Path, mime: str, size: int) -> Optional[Rule]:
        for rule in self.ruleset.sorted_rules():
            if self._rule_matches(rule, file_path, mime, size):
                return rule
        return None

    @staticmethod
    def _rule_matches(rule: Rule, file_path: Path, mime: str, size: int) -> bool:
        if rule.mime_types and not mime_matches(mime, rule.mime_types):
            return False
        if rule.extensions and file_path.suffix.lower() not in rule.extensions:
            return False
        if rule.name_contains:
            n = file_path.name.lower()
            if not any(s.lower() in n for s in rule.name_contains):
                return False
        if rule.name_regex:
            try:
                if not re.search(rule.name_regex, file_path.name, re.IGNORECASE):
                    return False
            except re.error:
                return False
        if rule.min_size_bytes is not None and size < rule.min_size_bytes:
            return False
        if rule.max_size_bytes is not None and size > rule.max_size_bytes:
            return False
        return True

    # ------------------------------------------------------------------ #
    def _resolve_root_and_rel(
        self, rule: Rule, file_path: Path
    ) -> tuple[Path, Path]:
        """Return (root, target_path) — root is used for containment checks."""
        now = datetime.now()
        tokens = {
            "year": f"{now.year:04d}",
            "month": f"{now.month:02d}",
            "day": f"{now.day:02d}",
            "name": file_path.stem,
            "ext": file_path.suffix.lstrip("."),
            "date": now.strftime("%Y-%m-%d"),
        }

        dest_str = rule.destination
        if not rule.organize_by_date:
            dest_str = dest_str.replace("/{year}", "").replace("/{month}", "")

        try:
            rel = dest_str.format(**tokens)
        except (KeyError, IndexError):
            rel = dest_str

        # --- filename --- #
        if rule.rename_pattern:
            try:
                new_name = rule.rename_pattern.format(**tokens)
            except (KeyError, IndexError):
                new_name = file_path.name
        else:
            new_name = file_path.name

        new_name = sanitize_component(new_name)
        if not Path(new_name).suffix and file_path.suffix:
            new_name += file_path.suffix

        # --- absolute vs. archive-relative --- #
        ABS = "__ABS__"
        if rel.startswith(ABS):
            root = Path(rel[len(ABS) :]).resolve(strict=False)
            target = root / new_name
        else:
            # Sanitize every path segment under the archive root
            clean_parts = [
                sanitize_component(p)
                for p in Path(rel).parts
                if p not in ("", ".")
            ]
            root = self.output_directory
            target = root.joinpath(*clean_parts) / new_name

        # --- final containment assertion --- #
        target = assert_inside(target, root) if target.parent == root else target
        # Guarantee the file lives under its root
        try:
            target.resolve(strict=False).relative_to(root.resolve(strict=False))
        except ValueError:
            raise ValueError(f"Refusing path outside root: {target}")

        return root, target