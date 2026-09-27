"""Cross-platform single-instance lock."""
from __future__ import annotations

import os
import sys
from pathlib import Path

from filesieve.utils.config import CONFIG_DIR, secure_mkdir


LOCK_FILE = CONFIG_DIR / "filesieve.lock"


class SingleInstance:
    def __init__(self) -> None:
        self._fd: int | None = None

    def acquire(self) -> bool:
        secure_mkdir(CONFIG_DIR)
        try:
            self._fd = os.open(str(LOCK_FILE), os.O_CREAT | os.O_RDWR, 0o600)
            if sys.platform == "win32":
                import msvcrt
                msvcrt.locking(self._fd, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self._fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            os.write(self._fd, str(os.getpid()).encode())
            os.ftruncate(self._fd, len(str(os.getpid())))
            return True
        except (OSError, IOError):
            if self._fd is not None:
                try:
                    os.close(self._fd)
                except OSError:
                    pass
                self._fd = None
            return False

    def release(self) -> None:
        if self._fd is None:
            return
        try:
            if sys.platform == "win32":
                import msvcrt
                msvcrt.locking(self._fd, msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self._fd, fcntl.LOCK_UN)
        except OSError:
            pass
        try:
            os.close(self._fd)
        except OSError:
            pass
        self._fd = None