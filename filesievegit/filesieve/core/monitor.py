"""Watchdog-based monitor with supervision, ignore-set, and settle-check."""

from __future__ import annotations

import threading   
import time
from pathlib import Path
from typing import Callable, Iterable
from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer
from watchdog.observers.api import BaseObserver

from filesieve.utils.logger import get_logger
from filesieve.utils.safe_io import file_is_stable, is_temp_file

logger = get_logger(__name__)


class _Handler(FileSystemEventHandler):
    """Watchdog handler that filters temporary files and forwards settled paths."""

    def __init__(
        self,
        callback: Callable[[Path], None],
        ignore_paths: Callable[[Path], bool],
  ) -> None:
        super().__init__()
        self._callback = callback
        self._ignore_paths = ignore_paths
        self._seen: dict[str, float] = {}
        self._lock = threading.Lock()

    def on_created(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        self._consider(Path(event.src_path))

    def on_moved(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        dest = getattr(event, "dest_path", None) or event.src_path
        self._consider(Path(dest))

    def _consider(self, path: Path) -> None:
        if is_temp_file(path):
            return
        if self._ignore_paths(path):
            return

        # De-dupe recent events
        now = time.monotonic()
        with self._lock:
            last = self._seen.get(str(path), 0.0)
            if now - last < 2.0:
                return
            self._seen[str(path)] = now
            if len(self._seen) > 5000:
                self._seen = {k: v for k, v in self._seen.items() if now - v < 30}

        threading.Thread(
            target=self._settle_then_callback, args=(path,), daemon=True
        ).start()

    def _settle_then_callback(self, path: Path) -> None:
        if not file_is_stable(path):
            logger.debug("File did not settle, skipping: %s", path)
            return
        try:
            self._callback(path)
        except Exception:
            logger.exception("Callback raised for %s", path)

class DirectoryMonitor:
    """Supervised watchdog observer with automatic restart on crash.

    Uses a generation counter so that a stale supervisor thread cannot
    fight with a newer one, and so that start() never has to tear down
    a still-running observer.
    """

    MAX_BACKOFF = 30.0

    def __init__(self, callback: Callable[[Path], None]) -> None:
        self._callback = callback
        self._observer: BaseObserver | None = None
        self._supervisor: threading.Thread | None = None
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._generation = 0
        self._directories: list[Path] = []
        self._recursive = False
        self._healthy = False
        self._last_error: str | None = None
        self._ignore_roots: set[Path] = set()

    # ------------------------------------------------------------------ #
    @property
    def is_running(self) -> bool:
        with self._lock:
            obs = self._observer
            return obs is not None and obs.is_alive()

    @property
    def is_healthy(self) -> bool:
        return self._healthy

    @property
    def last_error(self) -> str | None:
        return self._last_error

    def set_ignore_roots(self, roots: Iterable[Path]) -> None:
        with self._lock:
            self._ignore_roots = {r.resolve(strict=False) for r in roots}

    def _is_ignored(self, path: Path) -> bool:
        try:
            rp = path.resolve(strict=False)
        except OSError:
            return False

        with self._lock:
            roots = list(self._ignore_roots)

        for root in roots:
            # Safety: never treat a filesystem root (C:\, D:\, /) or a
            # user home directory as an ignore root. Those are almost
            # always configuration mistakes that would silently swallow
            # every file.
            try:
                if root == root.anchor:            # e.g. "C:\" or "/"
                    continue
                if root == root.parent:            # root has no parent
                    continue
            except Exception:
                continue

            # Must be strictly inside, not equal to, the root.
            if rp == root:
                continue

            try:
                rp.relative_to(root)
                return True
            except ValueError:
                continue
        return False

    # ------------------------------------------------------------------ #
    def start(self, directories: Iterable[Path], recursive: bool = False) -> None:
        """Start or reconfigure the monitor. Never tears down a running
        supervisor — it just bumps the generation so the running thread
        picks up the new config on its next loop iteration."""
        dirs = [Path(d) for d in directories]

        with self._lock:
            self._directories = dirs
            self._recursive = recursive
            self._generation += 1
            gen = self._generation

            # Already running? Just bump generation — don't restart.
            sup = self._supervisor
            if sup is not None and sup.is_alive():
                return

            # Otherwise spawn a fresh supervisor.
            self._stop_event = threading.Event()
            self._supervisor = threading.Thread(
                target=self._supervise,
                args=(gen,),
                name="FileSieveSupervisor",
                daemon=True,
            )
            self._supervisor.start()

    def stop(self) -> None:
        with self._lock:
            self._stop_event.set()
            obs = self._observer
            sup = self._supervisor
            self._observer = None
            self._supervisor = None

        if obs is not None:
            try:
                obs.stop()
                obs.join(timeout=3)
            except Exception:
                pass

        if sup is not None and sup.is_alive():
            try:
                sup.join(timeout=3)
            except Exception:
                pass

        self._healthy = False

    # ------------------------------------------------------------------ #
    def _supervise(self, generation: int) -> None:
        backoff = 1.0

        while not self._stop_event.is_set():
            # Has a newer start() superseded us?
            with self._lock:
                if generation != self._generation:
                    return
                directories = list(self._directories)
                recursive = self._recursive

            observer: BaseObserver | None = None
            try:
                observer = Observer()
                handler = _Handler(self._callback, self._is_ignored)

                watched = 0
                for directory in directories:
                    if not directory.exists() or not directory.is_dir():
                        logger.warning("Skipping invalid directory: %s", directory)
                        continue
                    try:
                        observer.schedule(handler, str(directory), recursive=recursive)
                        watched += 1
                    except OSError as exc:
                        logger.error("Failed to watch %s: %s", directory, exc)

                if watched == 0:
                    raise RuntimeError("No valid directories to watch")

                observer.daemon = True
                observer.start()

                # Commit to being the active observer — but only if
                # we haven't been superseded in the meantime.
                with self._lock:
                    if generation != self._generation:
                        try:
                            observer.stop()
                            observer.join(timeout=2)
                        except Exception:
                            pass
                        return
                    self._observer = observer
                    self._healthy = True
                    self._last_error = None

                logger.info("Monitoring %d director(ies)", watched)
                backoff = 1.0

                # Inner loop: stay alive while the observer runs.
                while not self._stop_event.is_set():
                    with self._lock:
                        if generation != self._generation:
                            return  # superseded
                    if not observer.is_alive():
                        raise RuntimeError("Observer thread died unexpectedly")
                    time.sleep(0.5)

                # stop() was called — clean exit.
                return

            except Exception as exc:
                if self._stop_event.is_set():
                    return
                with self._lock:
                    if generation != self._generation:
                        return  # superseded — exit quietly
                self._last_error = str(exc)
                self._healthy = False
                logger.error(
                    "Observer crashed: %s — restarting in %.1fs", exc, backoff
                )
                if self._stop_event.wait(backoff):
                    return
                backoff = min(backoff * 2, self.MAX_BACKOFF)

            finally:
                if observer is not None:
                    try:
                        observer.stop()
                        observer.join(timeout=2)
                    except Exception:
                        pass
                with self._lock:
                    if self._observer is observer:
                        self._observer = None