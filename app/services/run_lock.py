"""Cross-process lock preventing overlapping scheduled or CLI runs."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path


class ConcurrentRunError(RuntimeError):
    pass


class FileRunLock:
    def __init__(self, path: Path, stale_after_seconds: int = 4 * 60 * 60) -> None:
        self.path = path
        self.stale_after_seconds = stale_after_seconds
        self.acquired = False

    def is_active(self) -> bool:
        """Report an active lock while removing an expired lock record."""

        try:
            age = time.time() - self.path.stat().st_mtime
        except FileNotFoundError:
            return False
        if age > self.stale_after_seconds:
            self.path.unlink(missing_ok=True)
            return False
        return True

    def __enter__(self) -> FileRunLock:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.is_active()
        try:
            descriptor = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError as exc:
            raise ConcurrentRunError(f"Another pipeline run holds {self.path}") from exc
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump({"pid": os.getpid(), "started_at": time.time()}, handle)
        self.acquired = True
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        if self.acquired:
            self.path.unlink(missing_ok=True)
            self.acquired = False
