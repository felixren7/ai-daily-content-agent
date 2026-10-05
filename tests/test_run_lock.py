from __future__ import annotations

import pytest

from app.services.run_lock import ConcurrentRunError, FileRunLock


def test_run_lock_prevents_concurrent_execution(tmp_path) -> None:
    path = tmp_path / "pipeline.lock"
    with FileRunLock(path):
        with pytest.raises(ConcurrentRunError):
            with FileRunLock(path):
                pass
    assert not path.exists()
