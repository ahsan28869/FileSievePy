"""SQLite-backed journal for moves: undo history + crash recovery."""
from __future__ import annotations

import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional

from filesieve.utils.config import CONFIG_DIR, secure_mkdir
from filesieve.utils.logger import get_logger


logger = get_logger(__name__)

JOURNAL_DB = CONFIG_DIR / "journal.db"


_SCHEMA = """
CREATE TABLE IF NOT EXISTS moves (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    source       TEXT NOT NULL,
    destination  TEXT NOT NULL,
    rule_name    TEXT,
    moved_at     REAL NOT NULL,
    status       TEXT NOT NULL DEFAULT 'complete',  -- 'in_progress' | 'complete' | 'failed'
    error        TEXT
);
CREATE INDEX IF NOT EXISTS idx_moves_moved_at ON moves(moved_at DESC);
CREATE INDEX IF NOT EXISTS idx_moves_status   ON moves(status);
"""


class Journal:
    """Thread-safe move journal."""

    def __init__(self, db_path: Path = JOURNAL_DB) -> None:
        self._db_path = db_path
        self._lock = threading.Lock()
        secure_mkdir(self._db_path.parent)
        self._init_schema()

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            try:
                yield conn
                conn.commit()
            finally:
                conn.close()

    def _init_schema(self) -> None:
        with self._conn() as conn:
            conn.executescript(_SCHEMA)

    # ------------------------------------------------------------------ #
    def begin_move(self, source: Path, destination: Path, rule_name: Optional[str]) -> int:
        with self._conn() as conn:
            cur = conn.execute(
                "INSERT INTO moves(source, destination, rule_name, moved_at, status) "
                "VALUES (?, ?, ?, ?, 'in_progress')",
                (str(source), str(destination), rule_name, time.time()),
            )
            return int(cur.lastrowid or 0)

    def complete_move(self, move_id: int) -> None:
        with self._conn() as conn:
            conn.execute("UPDATE moves SET status='complete' WHERE id=?", (move_id,))

    def fail_move(self, move_id: int, error: str) -> None:
        with self._conn() as conn:
            conn.execute(
                "UPDATE moves SET status='failed', error=? WHERE id=?",
                (error[:500], move_id),
            )

    # ------------------------------------------------------------------ #
    def last_completed(self, n: int = 10) -> list[sqlite3.Row]:
        with self._conn() as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.execute(
                "SELECT * FROM moves WHERE status='complete' ORDER BY moved_at DESC LIMIT ?",
                (n,),
            )
            return cur.fetchall()

    def pending_or_in_progress(self) -> list[sqlite3.Row]:
        with self._conn() as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.execute(
                "SELECT * FROM moves WHERE status='in_progress' ORDER BY moved_at DESC"
            )
            return cur.fetchall()

    # ------------------------------------------------------------------ #
    def undo_last(self) -> Optional[tuple[Path, Path]]:
        """Move the most recent completed move back. Returns (dest, source) or None."""
        from filesieve.utils.safe_io import safe_move  # local to avoid cycle

        with self._conn() as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.execute(
                "SELECT * FROM moves WHERE status='complete' ORDER BY moved_at DESC LIMIT 1"
            )
            row = cur.fetchone()

        if row is None:
            return None

        src = Path(row["source"])
        dst = Path(row["destination"])
        if not dst.exists():
            logger.warning("Cannot undo: destination missing (%s)", dst)
            return None
        if src.exists():
            logger.warning("Cannot undo: source already occupied (%s)", src)
            return None

        src.parent.mkdir(parents=True, exist_ok=True)
        safe_move(dst, src)

        with self._conn() as conn:
            conn.execute("UPDATE moves SET status='reverted' WHERE id=?", (row["id"],))

        return dst, src

    # ------------------------------------------------------------------ #
    def reconcile_on_startup(self) -> list[tuple[str, str]]:
        """Return a list of (source, destination, action) records for recovery."""
        issues: list[tuple[str, str]] = []
        for row in self.pending_or_in_progress():
            src = Path(row["source"])
            dst = Path(row["destination"])
            if dst.exists() and not src.exists():
                self.complete_move(row["id"])
                issues.append((str(src), str(dst)))
            elif src.exists() and not dst.exists():
                self.fail_move(row["id"], "source still present after crash")
            else:
                self.fail_move(row["id"], "ambiguous state after crash")
        return issues

    def prune(self, keep_days: int = 90) -> None:
        cutoff = time.time() - keep_days * 86400
        with self._conn() as conn:
            conn.execute("DELETE FROM moves WHERE moved_at < ?", (cutoff,))