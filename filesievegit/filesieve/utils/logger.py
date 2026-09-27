"""Logging with rotation, secure permissions, optional redaction."""
from __future__ import annotations

import logging
import logging.handlers
import os
import re
import sys
from pathlib import Path

from filesieve.utils.config import CONFIG_DIR, secure_mkdir


LOG_DIR = CONFIG_DIR / "logs"
REDACT_FILENAMES = os.environ.get("FILESIEVE_REDACT_LOGS", "0") == "1"

# Filenames inside log messages get redacted when enabled
_FILENAME_RE = re.compile(r"([\w\-. ]+\.\w{1,6})")


def _redact(msg: str) -> str:
    if not REDACT_FILENAMES:
        return msg
    return _FILENAME_RE.sub("<redacted>", msg)


class _RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = _redact(str(record.msg))
        if record.args:
            record.args = tuple(
                _redact(a) if isinstance(a, str) else a for a in record.args
            )
        return True


def setup_logger(name: str = "filesieve", level: int = logging.INFO) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(level)
    logger.propagate = False

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    secure_mkdir(LOG_DIR)
    log_file = LOG_DIR / "filesieve.log"

    try:
        file_handler = logging.handlers.RotatingFileHandler(
            log_file, maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8"
        )
        file_handler.setFormatter(formatter)
        file_handler.addFilter(_RedactingFilter())
        logger.addHandler(file_handler)

        try:
            os.chmod(log_file, 0o600)
        except OSError:
            pass
    except OSError:
        pass

    # Console handler — only when a real stdout exists.
    # In a --windowed / --noconsole build, sys.stdout is None and this
    # would raise. Guard it.
    if sys.stdout is not None and sys.stderr is not None:
        try:
            console = logging.StreamHandler(sys.stdout)
            console.setFormatter(formatter)
            console.addFilter(_RedactingFilter())
            logger.addHandler(console)
        except Exception:
            pass

    return logger


def get_logger(name: str = "filesieve") -> logging.Logger:
    return setup_logger(name)