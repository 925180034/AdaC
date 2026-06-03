"""Static regression tests for task event streaming."""

from __future__ import annotations

from pathlib import Path


def test_sse_heartbeat_timeout_is_sixty_seconds() -> None:
    """SSE streams should avoid sending overly frequent heartbeats."""
    source = Path("adacascade/api/events.py").read_text()

    assert "asyncio.wait_for(queue.get(), timeout=60.0)" in source
    assert "asyncio.wait_for(queue.get(), timeout=10.0)" not in source


def test_sse_heartbeat_catches_builtin_and_asyncio_timeouts() -> None:
    """Python 3.10 compatibility requires catching both timeout names."""
    source = Path("adacascade/api/events.py").read_text()

    assert "except (TimeoutError, asyncio.TimeoutError):" in source
