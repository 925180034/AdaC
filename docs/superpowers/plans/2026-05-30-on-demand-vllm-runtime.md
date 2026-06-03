# On-Demand vLLM Runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the local vLLM backend start only when the user switches to Local model, stop when the user switches back to API model, and stop automatically after idle timeout so GPU memory is not occupied while unused.

**Architecture:** Add a focused process-local `LocalLlmRuntimeManager` that owns only AdaCascade-started vLLM subprocesses. Keep `adacascade.llm_runtime` responsible for active backend request configuration, and let the runtime API compose backend selection with local vLLM lifecycle status. The frontend keeps the Local/API segmented control but shows clearer startup/shutdown states and refetches runtime status while the local runtime is transitional.

**Tech Stack:** FastAPI, Pydantic Settings, asyncio, subprocess, httpx, OpenAI-compatible vLLM API, React 18, React Query, Vitest, pytest.

---

## File structure

### Backend files

- Modify: `adacascade/config.py`
  - Add vLLM lifecycle settings: idle timeout, startup timeout, shutdown grace, log path, start command, health poll interval.
- Create: `adacascade/local_llm_runtime.py`
  - Own managed vLLM subprocess lifecycle, readiness checks, local request accounting, idle shutdown, and safe runtime snapshots.
- Modify: `adacascade/llm_client.py`
  - Wrap local backend calls in request accounting so the manager never stops vLLM during active requests.
- Modify: `adacascade/api/routes/runtime.py`
  - Extend `/runtime/llm` responses with local vLLM status and manage startup/shutdown during runtime switching.
- Modify: `adacascade/api/app.py`
  - Start and stop the idle monitor during FastAPI lifespan.
- Modify: `scripts/start_llm.sh`
  - Keep current behavior; no functional change expected unless tests reveal the need for env-based log friendliness.

### Backend tests

- Modify: `tests/unit/test_llm_runtime.py`
  - Keep existing backend selection tests passing with the unchanged `llm_runtime` responsibility.
- Create: `tests/unit/test_local_llm_runtime.py`
  - Test manager state transitions, startup success, timeout/error, external local endpoint behavior, managed stop, idle stop, and request accounting.
- Create: `tests/unit/test_llm_client_local_tracking.py`
  - Test local request accounting wraps local LLM calls and is skipped for API backend calls.
- Modify: `tests/integration/test_runtime_llm_api.py`
  - Test extended runtime metadata and route-level local/API switching behavior with a fake manager.

### Frontend files

- Modify: `frontend/src/api/runtime.ts`
  - Add local runtime status fields to `LlmRuntimeInfo`.
- Modify: `frontend/src/features/workspace/i18n.ts`
  - Add copy for local startup and local shutdown labels.
- Modify: `frontend/src/features/workspace/WorkspaceToolbar.tsx`
  - Render Local/API buttons with explicit starting/stopping labels.
- Modify: `frontend/src/features/workspace/WorkspacePage.tsx`
  - Pass local runtime status to the toolbar and refetch while status is `starting` or `stopping`.

### Frontend tests

- Modify: `frontend/src/features/workspace/WorkspaceToolbar.test.tsx`
  - Test Local startup/shutdown labels and disabled states.
- Modify: `frontend/src/features/workspace/WorkspacePage.test.tsx`
  - Test extended runtime info, startup failure behavior, and transitional status refetch behavior.

### Documentation

- Modify: `deploy/README.md`
  - Document that vLLM no longer needs to be manually kept running for normal UI use, and list lifecycle env variables.

---

## Task 1: Add vLLM lifecycle settings

**Files:**
- Modify: `adacascade/config.py`
- Test: `tests/unit/test_config_vllm_runtime.py`

- [ ] **Step 1: Write the failing config test**

Create `tests/unit/test_config_vllm_runtime.py`:

```python
"""vLLM lifecycle configuration tests."""

from __future__ import annotations

from adacascade.config import Settings


def test_vllm_runtime_settings_have_safe_defaults() -> None:
    settings = Settings(_env_file=None)

    assert settings.VLLM_IDLE_TIMEOUT_SECONDS == 900
    assert settings.VLLM_STARTUP_TIMEOUT_SECONDS == 240
    assert settings.VLLM_SHUTDOWN_GRACE_SECONDS == 10
    assert settings.VLLM_HEALTH_POLL_SECONDS == 1.0
    assert settings.VLLM_LOG_PATH == "./data/logs/vllm.log"
    assert settings.VLLM_START_COMMAND == "bash scripts/start_llm.sh"
```

- [ ] **Step 2: Run the config test to verify it fails**

Run:

```bash
pytest tests/unit/test_config_vllm_runtime.py -q
```

Expected: FAIL with an `AttributeError` for `VLLM_IDLE_TIMEOUT_SECONDS` or another missing vLLM lifecycle setting.

- [ ] **Step 3: Add vLLM lifecycle settings**

In `adacascade/config.py`, add these fields immediately after the existing LLM fields:

```python
    VLLM_IDLE_TIMEOUT_SECONDS: int = 900
    VLLM_STARTUP_TIMEOUT_SECONDS: int = 240
    VLLM_SHUTDOWN_GRACE_SECONDS: int = 10
    VLLM_HEALTH_POLL_SECONDS: float = 1.0
    VLLM_LOG_PATH: str = "./data/logs/vllm.log"
    VLLM_START_COMMAND: str = "bash scripts/start_llm.sh"
```

- [ ] **Step 4: Run the config test to verify it passes**

Run:

```bash
pytest tests/unit/test_config_vllm_runtime.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit Task 1**

```bash
git add adacascade/config.py tests/unit/test_config_vllm_runtime.py
git commit -m "feat(runtime): add vllm lifecycle settings"
```

---

## Task 2: Build the local vLLM runtime manager

**Files:**
- Create: `adacascade/local_llm_runtime.py`
- Test: `tests/unit/test_local_llm_runtime.py`

- [ ] **Step 1: Write failing manager tests**

Create `tests/unit/test_local_llm_runtime.py`:

```python
"""Local vLLM process lifecycle manager tests."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import pytest

from adacascade.local_llm_runtime import LocalLlmRuntimeManager, LocalRuntimeError


class FakeProcess:
    def __init__(self, *, poll_values: list[int | None] | None = None) -> None:
        self.poll_values = poll_values or [None]
        self.terminated = False
        self.killed = False
        self.wait_calls = 0

    def poll(self) -> int | None:
        if len(self.poll_values) > 1:
            return self.poll_values.pop(0)
        return self.poll_values[0]

    def terminate(self) -> None:
        self.terminated = True
        self.poll_values = [0]

    def kill(self) -> None:
        self.killed = True
        self.poll_values = [0]

    def wait(self, timeout: float | None = None) -> int:
        self.wait_calls += 1
        if self.poll() is None:
            raise TimeoutError("still running")
        return 0


class ProbeSequence:
    def __init__(self, values: list[bool]) -> None:
        self.values = values
        self.calls = 0

    async def __call__(self, base_url: str) -> bool:
        self.calls += 1
        if len(self.values) > 1:
            return self.values.pop(0)
        return self.values[0]


async def instant_sleep(_: float) -> None:
    return None


def monotonic_sequence(values: list[float]) -> Callable[[], float]:
    remaining = list(values)

    def _next() -> float:
        if len(remaining) > 1:
            return remaining.pop(0)
        return remaining[0]

    return _next


def manager(
    tmp_path: Path,
    *,
    ready_probe: Callable[[str], Awaitable[bool]],
    popen_factory: Callable[..., FakeProcess] | None = None,
    monotonic: Callable[[], float] | None = None,
) -> LocalLlmRuntimeManager:
    return LocalLlmRuntimeManager(
        base_url="http://localhost:8000/v1",
        start_command="bash scripts/start_llm.sh",
        log_path=tmp_path / "vllm.log",
        idle_timeout_seconds=10,
        startup_timeout_seconds=3,
        shutdown_grace_seconds=1,
        health_poll_seconds=1,
        ready_probe=ready_probe,
        popen_factory=popen_factory or (lambda *args, **kwargs: FakeProcess()),
        sleep=instant_sleep,
        monotonic=monotonic or monotonic_sequence([0, 1, 2, 3, 4, 20]),
    )


@pytest.mark.anyio
async def test_snapshot_defaults_to_stopped(tmp_path: Path) -> None:
    runtime = manager(tmp_path, ready_probe=ProbeSequence([False]))

    assert runtime.snapshot() == {
        "local_status": "stopped",
        "local_ready": False,
        "local_last_error": None,
    }


@pytest.mark.anyio
async def test_ensure_ready_starts_managed_process_until_probe_succeeds(tmp_path: Path) -> None:
    processes: list[FakeProcess] = []

    def popen_factory(*args: Any, **kwargs: Any) -> FakeProcess:
        proc = FakeProcess()
        processes.append(proc)
        return proc

    runtime = manager(
        tmp_path,
        ready_probe=ProbeSequence([False, False, True]),
        popen_factory=popen_factory,
        monotonic=monotonic_sequence([0, 1, 2, 3]),
    )

    snapshot = await runtime.ensure_ready()

    assert len(processes) == 1
    assert snapshot["local_status"] == "ready"
    assert snapshot["local_ready"] is True
    assert snapshot["local_last_error"] is None


@pytest.mark.anyio
async def test_ensure_ready_uses_external_ready_endpoint_without_managing_process(tmp_path: Path) -> None:
    processes: list[FakeProcess] = []
    runtime = manager(
        tmp_path,
        ready_probe=ProbeSequence([True]),
        popen_factory=lambda *args, **kwargs: processes.append(FakeProcess()) or processes[-1],
    )

    snapshot = await runtime.ensure_ready()
    await runtime.stop_managed()

    assert processes == []
    assert snapshot["local_status"] == "ready"
    assert snapshot["local_ready"] is True
    assert runtime.snapshot()["local_status"] == "ready"


@pytest.mark.anyio
async def test_ensure_ready_times_out_and_reports_safe_error(tmp_path: Path) -> None:
    runtime = manager(
        tmp_path,
        ready_probe=ProbeSequence([False]),
        monotonic=monotonic_sequence([0, 1, 2, 4]),
    )

    with pytest.raises(LocalRuntimeError, match="Local vLLM startup timed out"):
        await runtime.ensure_ready()

    snapshot = runtime.snapshot()
    assert snapshot["local_status"] == "error"
    assert snapshot["local_ready"] is False
    assert snapshot["local_last_error"] == "Local vLLM startup timed out"


@pytest.mark.anyio
async def test_stop_managed_terminates_only_managed_process(tmp_path: Path) -> None:
    proc = FakeProcess()
    runtime = manager(
        tmp_path,
        ready_probe=ProbeSequence([False, True]),
        popen_factory=lambda *args, **kwargs: proc,
    )
    await runtime.ensure_ready()

    snapshot = await runtime.stop_managed()

    assert proc.terminated is True
    assert snapshot["local_status"] == "stopped"
    assert snapshot["local_ready"] is False


@pytest.mark.anyio
async def test_idle_shutdown_skips_active_requests(tmp_path: Path) -> None:
    proc = FakeProcess()
    runtime = manager(
        tmp_path,
        ready_probe=ProbeSequence([False, True]),
        popen_factory=lambda *args, **kwargs: proc,
        monotonic=monotonic_sequence([0, 1, 20, 21]),
    )
    await runtime.ensure_ready()

    with runtime.track_request("local"):
        stopped = await runtime.stop_if_idle()

    assert stopped is False
    assert proc.terminated is False


@pytest.mark.anyio
async def test_idle_shutdown_stops_managed_process_after_timeout(tmp_path: Path) -> None:
    proc = FakeProcess()
    runtime = manager(
        tmp_path,
        ready_probe=ProbeSequence([False, True]),
        popen_factory=lambda *args, **kwargs: proc,
        monotonic=monotonic_sequence([0, 1, 20, 21]),
    )
    await runtime.ensure_ready()

    stopped = await runtime.stop_if_idle()

    assert stopped is True
    assert proc.terminated is True
    assert runtime.snapshot()["local_status"] == "stopped"
```

- [ ] **Step 2: Run manager tests to verify they fail**

Run:

```bash
pytest tests/unit/test_local_llm_runtime.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'adacascade.local_llm_runtime'`.

- [ ] **Step 3: Create manager implementation**

Create `adacascade/local_llm_runtime.py`:

```python
"""Managed local vLLM runtime lifecycle."""

from __future__ import annotations

import asyncio
import shlex
import subprocess
import time
from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol, TypedDict

import httpx
import structlog

from adacascade.config import settings

log = structlog.get_logger(__name__)

LocalRuntimeStatus = Literal["stopped", "starting", "ready", "stopping", "error"]


class LocalRuntimeSnapshot(TypedDict):
    local_status: LocalRuntimeStatus
    local_ready: bool
    local_last_error: str | None


class LocalRuntimeError(RuntimeError):
    """Raised when the managed local vLLM runtime cannot become ready."""


class ProcessLike(Protocol):
    def poll(self) -> int | None: ...
    def terminate(self) -> None: ...
    def kill(self) -> None: ...
    def wait(self, timeout: float | None = None) -> int: ...


@dataclass
class _State:
    status: LocalRuntimeStatus = "stopped"
    last_error: str | None = None
    process: ProcessLike | None = None
    managed: bool = False
    last_used_at: float = 0.0
    active_requests: int = 0


async def _default_ready_probe(base_url: str) -> bool:
    """Return whether the local OpenAI-compatible models endpoint is ready."""
    url = f"{base_url.rstrip('/')}/models"
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            response = await client.get(url)
        return response.status_code == 200
    except httpx.HTTPError:
        return False


class LocalLlmRuntimeManager:
    """Own lifecycle for vLLM processes started by AdaCascade."""

    def __init__(
        self,
        *,
        base_url: str,
        start_command: str,
        log_path: str | Path,
        idle_timeout_seconds: float,
        startup_timeout_seconds: float,
        shutdown_grace_seconds: float,
        health_poll_seconds: float,
        ready_probe: Callable[[str], Awaitable[bool]] = _default_ready_probe,
        popen_factory: Callable[..., ProcessLike] = subprocess.Popen,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self.base_url = base_url
        self.start_command = start_command
        self.log_path = Path(log_path)
        self.idle_timeout_seconds = idle_timeout_seconds
        self.startup_timeout_seconds = startup_timeout_seconds
        self.shutdown_grace_seconds = shutdown_grace_seconds
        self.health_poll_seconds = health_poll_seconds
        self._ready_probe = ready_probe
        self._popen_factory = popen_factory
        self._sleep = sleep
        self._monotonic = monotonic
        self._lock = asyncio.Lock()
        self._state = _State(last_used_at=monotonic())

    @classmethod
    def from_settings(cls) -> "LocalLlmRuntimeManager":
        """Build a manager from process settings."""
        return cls(
            base_url=settings.LLM_LOCAL_BASE_URL,
            start_command=settings.VLLM_START_COMMAND,
            log_path=settings.VLLM_LOG_PATH,
            idle_timeout_seconds=settings.VLLM_IDLE_TIMEOUT_SECONDS,
            startup_timeout_seconds=settings.VLLM_STARTUP_TIMEOUT_SECONDS,
            shutdown_grace_seconds=settings.VLLM_SHUTDOWN_GRACE_SECONDS,
            health_poll_seconds=settings.VLLM_HEALTH_POLL_SECONDS,
        )

    def snapshot(self) -> LocalRuntimeSnapshot:
        """Return safe local runtime state."""
        return {
            "local_status": self._state.status,
            "local_ready": self._state.status == "ready",
            "local_last_error": self._state.last_error,
        }

    async def ensure_ready(self) -> LocalRuntimeSnapshot:
        """Start managed vLLM if needed and wait until the local endpoint is ready."""
        async with self._lock:
            if await self._ready_probe(self.base_url):
                self._state.status = "ready"
                self._state.last_error = None
                self._state.last_used_at = self._monotonic()
                return self.snapshot()

            if self._state.process is None or self._state.process.poll() is not None:
                self._start_process()

            deadline = self._monotonic() + self.startup_timeout_seconds
            while self._monotonic() <= deadline:
                process = self._state.process
                if process is not None and process.poll() is not None:
                    self._set_error("Local vLLM exited before becoming ready")
                    raise LocalRuntimeError("Local vLLM exited before becoming ready")
                if await self._ready_probe(self.base_url):
                    self._state.status = "ready"
                    self._state.last_error = None
                    self._state.last_used_at = self._monotonic()
                    return self.snapshot()
                await self._sleep(self.health_poll_seconds)

            self._set_error("Local vLLM startup timed out")
            raise LocalRuntimeError("Local vLLM startup timed out")

    async def stop_managed(self) -> LocalRuntimeSnapshot:
        """Stop only the managed vLLM process started by this manager."""
        async with self._lock:
            return await self._stop_managed_locked()

    async def stop_if_idle(self) -> bool:
        """Stop managed vLLM when no local request is active and idle timeout elapsed."""
        async with self._lock:
            if not self._state.managed or self._state.process is None:
                return False
            if self._state.active_requests > 0:
                return False
            idle_for = self._monotonic() - self._state.last_used_at
            if idle_for < self.idle_timeout_seconds:
                return False
            await self._stop_managed_locked()
            return True

    @contextmanager
    def track_request(self, backend: str) -> Iterator[None]:
        """Track local LLM request activity for idle shutdown safety."""
        if backend != "local":
            yield
            return

        self._state.active_requests += 1
        try:
            yield
        finally:
            self._state.active_requests = max(0, self._state.active_requests - 1)
            self._state.last_used_at = self._monotonic()

    def _start_process(self) -> None:
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        log_file = self.log_path.open("ab")
        command = shlex.split(self.start_command)
        self._state.status = "starting"
        self._state.last_error = None
        self._state.process = self._popen_factory(
            command,
            cwd=Path(__file__).resolve().parent.parent,
            stdout=log_file,
            stderr=subprocess.STDOUT,
        )
        self._state.managed = True
        log.info("vllm.start", command=self.start_command, log_path=str(self.log_path))

    async def _stop_managed_locked(self) -> LocalRuntimeSnapshot:
        process = self._state.process
        if not self._state.managed or process is None:
            return self.snapshot()

        self._state.status = "stopping"
        process.terminate()
        try:
            process.wait(timeout=self.shutdown_grace_seconds)
        except Exception:
            process.kill()
            process.wait(timeout=None)

        self._state = _State(status="stopped", last_used_at=self._monotonic())
        log.info("vllm.stop")
        return self.snapshot()

    def _set_error(self, message: str) -> None:
        self._state.status = "error"
        self._state.last_error = message
        self._state.last_used_at = self._monotonic()


_manager: LocalLlmRuntimeManager | None = None


def get_manager() -> LocalLlmRuntimeManager:
    """Return the process-local manager singleton."""
    global _manager
    if _manager is None:
        _manager = LocalLlmRuntimeManager.from_settings()
    return _manager


def set_manager_for_tests(manager: LocalLlmRuntimeManager | None) -> None:
    """Replace the process-local manager during tests."""
    global _manager
    _manager = manager
```

- [ ] **Step 4: Run manager tests to verify they pass**

Run:

```bash
pytest tests/unit/test_local_llm_runtime.py -q
```

Expected: PASS.

- [ ] **Step 5: Run existing LLM runtime tests**

Run:

```bash
pytest tests/unit/test_llm_runtime.py -q
```

Expected: PASS. Existing backend selection behavior should remain unchanged.

- [ ] **Step 6: Commit Task 2**

```bash
git add adacascade/local_llm_runtime.py tests/unit/test_local_llm_runtime.py
git commit -m "feat(runtime): manage local vllm process lifecycle"
```

---

## Task 3: Extend runtime API metadata and switching behavior

**Files:**
- Modify: `adacascade/api/routes/runtime.py`
- Modify: `tests/integration/test_runtime_llm_api.py`

- [ ] **Step 1: Write failing route tests for local runtime metadata and switching**

Modify `tests/integration/test_runtime_llm_api.py`. Add this fake manager near the top, below `AUTH_HEADERS`:

```python
class FakeLocalRuntimeManager:
    def __init__(self) -> None:
        self.ensure_ready_calls = 0
        self.stop_managed_calls = 0
        self.snapshot_payload = {
            "local_status": "stopped",
            "local_ready": False,
            "local_last_error": None,
        }

    def snapshot(self) -> dict[str, object]:
        return dict(self.snapshot_payload)

    async def ensure_ready(self) -> dict[str, object]:
        self.ensure_ready_calls += 1
        self.snapshot_payload = {
            "local_status": "ready",
            "local_ready": True,
            "local_last_error": None,
        }
        return self.snapshot()

    async def stop_managed(self) -> dict[str, object]:
        self.stop_managed_calls += 1
        self.snapshot_payload = {
            "local_status": "stopped",
            "local_ready": False,
            "local_last_error": None,
        }
        return self.snapshot()
```

Update the `client` fixture to install the fake manager:

```python
@pytest.fixture()
def client() -> TestClient:
    mock_qdrant = MagicMock()
    raw_qdrant_mock = AsyncMock()
    fake_manager = FakeLocalRuntimeManager()
    with (
        patch("qdrant_client.AsyncQdrantClient", return_value=raw_qdrant_mock),
        patch("adacascade.api.app.AdacQdrantClient", return_value=mock_qdrant),
        patch(
            "adacascade.api.app.reconcile_orphan_ingests", new=AsyncMock(return_value=0)
        ),
        patch("adacascade.local_llm_runtime.get_manager", return_value=fake_manager),
    ):
        from adacascade import llm_runtime
        from adacascade.api.app import app

        llm_runtime.set_active_backend("local")
        app.state.fake_local_runtime_manager = fake_manager
        try:
            with TestClient(app, raise_server_exceptions=False) as c:
                yield c
        finally:
            llm_runtime.set_active_backend("local")
```

Add these tests:

```python
def test_runtime_llm_get_returns_local_lifecycle_metadata(client: TestClient) -> None:
    resp = client.get("/runtime/llm", headers=AUTH_HEADERS)

    assert resp.status_code == 200
    body = resp.json()
    assert body["backend"] == "local"
    assert body["local_status"] == "stopped"
    assert body["local_ready"] is False
    assert body["local_last_error"] is None


def test_runtime_llm_put_local_waits_until_local_runtime_ready(client: TestClient) -> None:
    resp = client.put("/runtime/llm", headers=AUTH_HEADERS, json={"backend": "local"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["backend"] == "local"
    assert body["local_status"] == "ready"
    assert body["local_ready"] is True
    assert client.app.state.fake_local_runtime_manager.ensure_ready_calls == 1


def test_runtime_llm_put_api_stops_managed_local_runtime(client: TestClient) -> None:
    resp = client.put("/runtime/llm", headers=AUTH_HEADERS, json={"backend": "api"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["backend"] == "api"
    assert body["local_status"] == "stopped"
    assert body["local_ready"] is False
    assert client.app.state.fake_local_runtime_manager.stop_managed_calls == 1
```

- [ ] **Step 2: Run route tests to verify they fail**

Run:

```bash
pytest tests/integration/test_runtime_llm_api.py -q
```

Expected: FAIL because `LlmRuntimeInfo` does not include `local_status`, `local_ready`, and `local_last_error`, and `PUT local` does not call the manager.

- [ ] **Step 3: Extend runtime API route**

Modify `adacascade/api/routes/runtime.py` to this shape:

```python
"""Runtime configuration API routes."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from adacascade import llm_runtime, local_llm_runtime

router = APIRouter(prefix="/runtime", tags=["runtime"])


class LlmRuntimeInfo(BaseModel):
    backend: Literal["local", "api"]
    base_url: str
    model: str
    api_key_configured: bool
    local_status: Literal["stopped", "starting", "ready", "stopping", "error"]
    local_ready: bool
    local_last_error: str | None


class LlmRuntimeUpdate(BaseModel):
    backend: Literal["local", "api"]


def _runtime_info() -> LlmRuntimeInfo:
    payload = {
        **llm_runtime.get_runtime_info(),
        **local_llm_runtime.get_manager().snapshot(),
    }
    return LlmRuntimeInfo.model_validate(payload)


@router.get("/llm")
async def get_llm_runtime() -> LlmRuntimeInfo:
    """Return safe LLM runtime metadata."""
    return _runtime_info()


@router.put("/llm")
async def update_llm_runtime(payload: LlmRuntimeUpdate) -> LlmRuntimeInfo:
    """Switch the process-local LLM runtime backend."""
    manager = local_llm_runtime.get_manager()
    try:
        if payload.backend == "local":
            await manager.ensure_ready()
            llm_runtime.set_active_backend("local")
            return _runtime_info()

        llm_runtime.set_active_backend("api")
        await manager.stop_managed()
        return _runtime_info()
    except local_llm_runtime.LocalRuntimeError as exc:
        llm_runtime.set_active_backend("api")
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
```

- [ ] **Step 4: Run route tests to verify they pass**

Run:

```bash
pytest tests/integration/test_runtime_llm_api.py -q
```

Expected: PASS.

- [ ] **Step 5: Run unit runtime tests to catch response shape regressions**

Run:

```bash
pytest tests/unit/test_llm_runtime.py tests/unit/test_local_llm_runtime.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit Task 3**

```bash
git add adacascade/api/routes/runtime.py tests/integration/test_runtime_llm_api.py
git commit -m "feat(runtime): expose managed local vllm status"
```

---

## Task 4: Add idle monitor to FastAPI lifespan

**Files:**
- Modify: `adacascade/api/app.py`
- Test: `tests/integration/test_runtime_llm_api.py`

- [ ] **Step 1: Write a failing lifespan test for idle monitor startup and shutdown**

In `tests/integration/test_runtime_llm_api.py`, extend `FakeLocalRuntimeManager`:

```python
    async def idle_monitor_loop(self) -> None:
        self.idle_monitor_started = True
        await self.idle_monitor_event.wait()
```

Also update its `__init__`:

```python
        self.idle_monitor_started = False
        self.idle_monitor_event = AsyncMock()
        self.idle_monitor_event.wait = AsyncMock()
```

Add this test:

```python
def test_runtime_lifespan_starts_idle_monitor(client: TestClient) -> None:
    manager = client.app.state.fake_local_runtime_manager

    assert manager.idle_monitor_started is True
```

- [ ] **Step 2: Run the lifespan test to verify it fails**

Run:

```bash
pytest tests/integration/test_runtime_llm_api.py::test_runtime_lifespan_starts_idle_monitor -q
```

Expected: FAIL because the app lifespan does not start a vLLM idle monitor.

- [ ] **Step 3: Implement idle monitor loop on the manager**

In `adacascade/local_llm_runtime.py`, add this method to `LocalLlmRuntimeManager`:

```python
    async def idle_monitor_loop(self) -> None:
        """Periodically stop managed vLLM after the configured idle timeout."""
        while True:
            await self._sleep(min(30.0, max(1.0, self.health_poll_seconds)))
            await self.stop_if_idle()
```

- [ ] **Step 4: Start and cancel idle monitor in lifespan**

Modify `adacascade/api/app.py`:

Add imports:

```python
import asyncio
from contextlib import asynccontextmanager, suppress
```

Add this import:

```python
from adacascade import local_llm_runtime
```

Inside `lifespan`, after Qdrant registry initialization and before the checkpoint block, add:

```python
    local_llm_manager = local_llm_runtime.get_manager()
    app.state.local_llm_manager = local_llm_manager
    app.state.local_llm_idle_monitor = asyncio.create_task(
        local_llm_manager.idle_monitor_loop()
    )
```

Replace the cleanup section after the checkpoint block with:

```python
    # ── Cleanup ───────────────────────────────────────────────────────────────
    app.state.local_llm_idle_monitor.cancel()
    with suppress(asyncio.CancelledError):
        await app.state.local_llm_idle_monitor
    await app.state.local_llm_manager.stop_managed()
    await raw_qdrant.close()
    log.info("app.shutdown")
```

- [ ] **Step 5: Run lifespan test to verify it passes**

Run:

```bash
pytest tests/integration/test_runtime_llm_api.py::test_runtime_lifespan_starts_idle_monitor -q
```

Expected: PASS.

- [ ] **Step 6: Run runtime integration tests**

Run:

```bash
pytest tests/integration/test_runtime_llm_api.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit Task 4**

```bash
git add adacascade/api/app.py adacascade/local_llm_runtime.py tests/integration/test_runtime_llm_api.py
git commit -m "feat(runtime): stop managed vllm after idle timeout"
```

---

## Task 5: Track local LLM requests in `llm_client.chat`

**Files:**
- Modify: `adacascade/llm_client.py`
- Test: `tests/unit/test_llm_client_local_tracking.py`

- [ ] **Step 1: Write failing request tracking tests**

Create `tests/unit/test_llm_client_local_tracking.py`:

```python
"""LLM client local runtime accounting tests."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator
from unittest.mock import MagicMock

from adacascade import llm_client, llm_runtime


class FakeManager:
    def __init__(self) -> None:
        self.backends: list[str] = []

    @contextmanager
    def track_request(self, backend: str) -> Iterator[None]:
        self.backends.append(backend)
        yield


class FakeCompletions:
    def create(self, **kwargs):  # type: ignore[no-untyped-def]
        return MagicMock(kwargs=kwargs)


class FakeChat:
    def __init__(self) -> None:
        self.completions = FakeCompletions()


class FakeClient:
    def __init__(self) -> None:
        self.chat = FakeChat()


def test_chat_tracks_local_backend_requests(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    manager = FakeManager()
    llm_runtime.set_active_backend("local")
    monkeypatch.setattr(llm_client.local_llm_runtime, "get_manager", lambda: manager)
    monkeypatch.setattr(llm_client, "_client_for_config", lambda config: FakeClient())

    llm_client.chat([{"role": "user", "content": "hello"}])

    assert manager.backends == ["local"]


def test_chat_tracks_api_backend_without_local_active_count(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    manager = FakeManager()
    llm_runtime.set_active_backend("api")
    monkeypatch.setattr(llm_client.local_llm_runtime, "get_manager", lambda: manager)
    monkeypatch.setattr(llm_client, "_client_for_config", lambda config: FakeClient())

    llm_client.chat([{"role": "user", "content": "hello"}])

    assert manager.backends == ["api"]
```

- [ ] **Step 2: Run tracking tests to verify they fail**

Run:

```bash
pytest tests/unit/test_llm_client_local_tracking.py -q
```

Expected: FAIL because `llm_client` does not import or call `local_llm_runtime.get_manager().track_request()`.

- [ ] **Step 3: Wrap chat completion call in request tracking**

Modify `adacascade/llm_client.py`:

Add the import:

```python
from adacascade import llm_runtime, local_llm_runtime
```

Replace the final completion call with:

```python
    with local_llm_runtime.get_manager().track_request(runtime_config.backend):
        resp = client.chat.completions.create(
            **request_kwargs,
        )
    return cast(ChatCompletion, resp)
```

- [ ] **Step 4: Run tracking tests to verify they pass**

Run:

```bash
pytest tests/unit/test_llm_client_local_tracking.py -q
```

Expected: PASS.

- [ ] **Step 5: Run LLM-related unit tests**

Run:

```bash
pytest tests/unit/test_llm_runtime.py tests/unit/test_local_llm_runtime.py tests/unit/test_llm_client_local_tracking.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit Task 5**

```bash
git add adacascade/llm_client.py tests/unit/test_llm_client_local_tracking.py
git commit -m "feat(runtime): track local llm request activity"
```

---

## Task 6: Update frontend runtime types and toolbar states

**Files:**
- Modify: `frontend/src/api/runtime.ts`
- Modify: `frontend/src/features/workspace/i18n.ts`
- Modify: `frontend/src/features/workspace/WorkspaceToolbar.tsx`
- Modify: `frontend/src/features/workspace/WorkspaceToolbar.test.tsx`

- [ ] **Step 1: Write failing toolbar tests for startup and shutdown labels**

Modify the `copy` object in `frontend/src/features/workspace/WorkspaceToolbar.test.tsx`:

```ts
const copy = {
  preferencesLabel: 'Workspace preferences',
  language: 'Language',
  english: 'English',
  chinese: '中文',
  theme: 'Theme',
  light: 'Light',
  dark: 'Dark',
  modelRuntime: 'Model runtime',
  localModel: 'Local vLLM',
  apiModel: 'DeepSeek API',
  runtimeSwitching: 'Switching runtime…',
  runtimeStartingLocal: 'Starting local model…',
  runtimeStoppingLocal: 'Stopping local model…',
  runtimeLoadError: 'Runtime status is unavailable.',
  runtimeSwitchError: 'Runtime switch failed.',
}
```

Add these tests:

```tsx
  it('shows local startup text while local vLLM is starting', () => {
    render(
      <WorkspaceToolbar
        copy={copy}
        language="en"
        theme="light"
        runtimeBackend="api"
        localRuntimeStatus="starting"
        isRuntimePending={false}
        isRunning={false}
        onLanguageChange={vi.fn()}
        onThemeChange={vi.fn()}
        onRuntimeBackendChange={vi.fn()}
      />,
    )

    expect(screen.getByRole('button', { name: 'Starting local model…', pressed: false })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'DeepSeek API', pressed: true })).toBeDisabled()
  })

  it('shows local shutdown text while local vLLM is stopping', () => {
    render(
      <WorkspaceToolbar
        copy={copy}
        language="en"
        theme="light"
        runtimeBackend="api"
        localRuntimeStatus="stopping"
        isRuntimePending={false}
        isRunning={false}
        onLanguageChange={vi.fn()}
        onThemeChange={vi.fn()}
        onRuntimeBackendChange={vi.fn()}
      />,
    )

    expect(screen.getByRole('button', { name: 'Stopping local model…', pressed: false })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'DeepSeek API', pressed: true })).toBeDisabled()
  })
```

- [ ] **Step 2: Run toolbar tests to verify they fail**

Run:

```bash
npm --prefix frontend run test -- WorkspaceToolbar.test.tsx --run
```

Expected: FAIL because `WorkspaceToolbarCopy` and `WorkspaceToolbarProps` do not include local runtime status labels or props.

- [ ] **Step 3: Extend runtime API types**

Modify `frontend/src/api/runtime.ts`:

```ts
import { apiJson } from './client'

export type RuntimeBackend = 'local' | 'api'
export type LocalRuntimeStatus = 'stopped' | 'starting' | 'ready' | 'stopping' | 'error'

export type LlmRuntimeInfo = {
  backend: RuntimeBackend
  base_url: string
  model: string
  api_key_configured: boolean
  local_status: LocalRuntimeStatus
  local_ready: boolean
  local_last_error: string | null
}

export function getLlmRuntime(tenantId: string): Promise<LlmRuntimeInfo> {
  return apiJson<LlmRuntimeInfo>('/runtime/llm', tenantId)
}

export function updateLlmRuntime(tenantId: string, backend: RuntimeBackend): Promise<LlmRuntimeInfo> {
  return apiJson<LlmRuntimeInfo>('/runtime/llm', tenantId, {
    method: 'PUT',
    body: JSON.stringify({ backend }),
  })
}
```

- [ ] **Step 4: Extend toolbar copy and props**

Modify `frontend/src/features/workspace/WorkspaceToolbar.tsx`:

```tsx
import type { LocalRuntimeStatus, RuntimeBackend } from '../../api/runtime'
```

Add copy fields:

```ts
  runtimeStartingLocal: string
  runtimeStoppingLocal: string
```

Add prop:

```ts
  localRuntimeStatus?: LocalRuntimeStatus | null
```

Update the component parameter list to include `localRuntimeStatus = null`.

Replace runtime disabled and label logic with:

```tsx
  const isLocalTransitional = localRuntimeStatus === 'starting' || localRuntimeStatus === 'stopping'
  const runtimeDisabled = isRuntimeDisabled || isRunning || isRuntimePending || runtimeBackend === null || isLocalTransitional
  const localRuntimeLabel =
    localRuntimeStatus === 'starting'
      ? copy.runtimeStartingLocal
      : localRuntimeStatus === 'stopping'
        ? copy.runtimeStoppingLocal
        : isRuntimePending && pendingRuntimeBackend === 'local'
          ? copy.runtimeStartingLocal
          : copy.localModel
  const apiRuntimeLabel = isRuntimePending && pendingRuntimeBackend === 'api' ? copy.runtimeStoppingLocal : copy.apiModel
```

Use `localRuntimeLabel` for the Local button and `apiRuntimeLabel` for the API button.

- [ ] **Step 5: Add i18n copy**

Modify `frontend/src/features/workspace/i18n.ts`.

Add to the `toolbar` type:

```ts
    runtimeStartingLocal: string
    runtimeStoppingLocal: string
```

Add English copy near `runtimeSwitching`:

```ts
      runtimeStartingLocal: 'Starting local model…',
      runtimeStoppingLocal: 'Stopping local model…',
```

Add Chinese copy near `runtimeSwitching`:

```ts
      runtimeStartingLocal: '正在启动本地模型…',
      runtimeStoppingLocal: '正在停止本地模型…',
```

- [ ] **Step 6: Run toolbar tests to verify they pass**

Run:

```bash
npm --prefix frontend run test -- WorkspaceToolbar.test.tsx --run
```

Expected: PASS.

- [ ] **Step 7: Commit Task 6**

```bash
git add frontend/src/api/runtime.ts frontend/src/features/workspace/i18n.ts frontend/src/features/workspace/WorkspaceToolbar.tsx frontend/src/features/workspace/WorkspaceToolbar.test.tsx
git commit -m "feat(frontend): show managed local runtime states"
```

---

## Task 7: Refetch frontend runtime status during transitional states

**Files:**
- Modify: `frontend/src/features/workspace/WorkspacePage.tsx`
- Modify: `frontend/src/features/workspace/WorkspacePage.test.tsx`

- [ ] **Step 1: Update test fixtures for extended runtime info**

In `frontend/src/features/workspace/WorkspacePage.test.tsx`, update `localRuntime` and `apiRuntime` fixtures so they include all fields:

```ts
const localRuntime: LlmRuntimeInfo = {
  backend: 'local',
  base_url: 'http://localhost:8000/v1',
  model: 'qwen3:8b',
  api_key_configured: true,
  local_status: 'ready',
  local_ready: true,
  local_last_error: null,
}

const apiRuntime: LlmRuntimeInfo = {
  backend: 'api',
  base_url: 'https://api.deepseek.com/v1',
  model: 'deepseek-v4-flash',
  api_key_configured: true,
  local_status: 'stopped',
  local_ready: false,
  local_last_error: null,
}
```

Add this fixture:

```ts
const startingRuntime: LlmRuntimeInfo = {
  backend: 'api',
  base_url: 'https://api.deepseek.com/v1',
  model: 'deepseek-v4-flash',
  api_key_configured: true,
  local_status: 'starting',
  local_ready: false,
  local_last_error: null,
}
```

- [ ] **Step 2: Add failing WorkspacePage test for transitional UI**

Add this test near the existing runtime tests:

```tsx
  it('passes local transitional status to the toolbar while runtime is starting', async () => {
    vi.mocked(getLlmRuntime).mockResolvedValue(startingRuntime)
    renderWorkspace()

    expect(await screen.findByRole('button', { name: 'Starting local model…', pressed: false })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'API model', pressed: true })).toBeDisabled()
  })
```

- [ ] **Step 3: Run WorkspacePage test to verify it fails**

Run:

```bash
npm --prefix frontend run test -- WorkspacePage.test.tsx --run
```

Expected: FAIL because `WorkspacePage` does not pass `localRuntimeStatus` to `WorkspaceToolbar` and fixtures do not match the old type until implementation is complete.

- [ ] **Step 4: Pass local runtime status into toolbar**

Modify `frontend/src/features/workspace/WorkspacePage.tsx`:

Add this after `runtimeBackend`:

```ts
  const localRuntimeStatus = runtimeQuery.data?.local_status ?? null
```

Update `useQuery` for runtime:

```ts
  const runtimeQuery = useQuery({
    queryKey: ['llm-runtime', tenantId],
    queryFn: () => getLlmRuntime(tenantId),
    refetchInterval: (query) => {
      const status = query.state.data?.local_status
      return status === 'starting' || status === 'stopping' ? 1000 : false
    },
  })
```

Update the `WorkspaceToolbar` props:

```tsx
        localRuntimeStatus={localRuntimeStatus}
```

- [ ] **Step 5: Make runtime mutation errors preserve API selection**

In `WorkspacePage.tsx`, update runtime mutation `onError`:

```ts
    onError: () => {
      setRuntimeError(copy.toolbar.runtimeSwitchError)
      void queryClient.invalidateQueries({ queryKey: ['llm-runtime', tenantId] })
    },
```

This ensures a failed local startup refetches server state, which should remain API.

- [ ] **Step 6: Run WorkspacePage tests**

Run:

```bash
npm --prefix frontend run test -- WorkspacePage.test.tsx --run
```

Expected: PASS.

- [ ] **Step 7: Run frontend runtime-related tests**

Run:

```bash
npm --prefix frontend run test -- WorkspaceToolbar.test.tsx WorkspacePage.test.tsx --run
```

Expected: PASS.

- [ ] **Step 8: Commit Task 7**

```bash
git add frontend/src/features/workspace/WorkspacePage.tsx frontend/src/features/workspace/WorkspacePage.test.tsx
git commit -m "feat(frontend): poll transitional local runtime status"
```

---

## Task 8: Document on-demand vLLM operation

**Files:**
- Modify: `deploy/README.md`
- Modify: `.env.example`

- [ ] **Step 1: Add failing documentation/config test for env example**

Create `tests/unit/test_env_example_vllm.py`:

```python
"""Deployment environment example coverage for managed vLLM settings."""

from __future__ import annotations

from pathlib import Path


def test_env_example_documents_managed_vllm_settings() -> None:
    env_example = Path(".env.example").read_text()

    assert "VLLM_IDLE_TIMEOUT_SECONDS=900" in env_example
    assert "VLLM_STARTUP_TIMEOUT_SECONDS=240" in env_example
    assert "VLLM_SHUTDOWN_GRACE_SECONDS=10" in env_example
    assert "VLLM_LOG_PATH=/app/data/logs/vllm.log" in env_example
    assert "VLLM_START_COMMAND=bash scripts/start_llm.sh" in env_example
```

- [ ] **Step 2: Run env example test to verify it fails**

Run:

```bash
pytest tests/unit/test_env_example_vllm.py -q
```

Expected: FAIL because `.env.example` does not list the managed vLLM variables.

- [ ] **Step 3: Update `.env.example`**

Append this section near the LLM settings:

```dotenv
# Managed local vLLM lifecycle. Local vLLM starts when selecting Local model
# and is stopped when switching back to API model or after idle timeout.
VLLM_IDLE_TIMEOUT_SECONDS=900
VLLM_STARTUP_TIMEOUT_SECONDS=240
VLLM_SHUTDOWN_GRACE_SECONDS=10
VLLM_HEALTH_POLL_SECONDS=1.0
VLLM_LOG_PATH=/app/data/logs/vllm.log
VLLM_START_COMMAND=bash scripts/start_llm.sh
```

- [ ] **Step 4: Update deployment README**

In `deploy/README.md`, add this section under the LLM configuration notes:

```markdown
### Managed local vLLM lifecycle

AdaCascade can manage local vLLM on demand. With the default UI flow, selecting **Local model** starts vLLM through `VLLM_START_COMMAND`, waits for `LLM_LOCAL_BASE_URL/v1/models`, and only then switches the active backend to local. Selecting **API model** stops the vLLM process if AdaCascade started it.

Default lifecycle values:

- `VLLM_IDLE_TIMEOUT_SECONDS=900` — release GPU after 15 minutes of local-model inactivity.
- `VLLM_STARTUP_TIMEOUT_SECONDS=240` — maximum wait for vLLM readiness.
- `VLLM_SHUTDOWN_GRACE_SECONDS=10` — graceful stop window before kill.
- `VLLM_LOG_PATH=/app/data/logs/vllm.log` — vLLM stdout/stderr log path.
- `VLLM_START_COMMAND=bash scripts/start_llm.sh` — command used by the API process to start vLLM.

If vLLM is already running because an operator started it manually, AdaCascade may use it as a ready local endpoint, but it will not stop that external process.
```

- [ ] **Step 5: Run documentation/config test**

Run:

```bash
pytest tests/unit/test_env_example_vllm.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit Task 8**

```bash
git add .env.example deploy/README.md tests/unit/test_env_example_vllm.py
git commit -m "docs(runtime): document managed local vllm lifecycle"
```

---

## Task 9: End-to-end verification

**Files:**
- No source files modified in this task.

- [ ] **Step 1: Run backend unit tests for runtime lifecycle**

Run:

```bash
pytest tests/unit/test_config_vllm_runtime.py tests/unit/test_llm_runtime.py tests/unit/test_local_llm_runtime.py tests/unit/test_llm_client_local_tracking.py tests/unit/test_env_example_vllm.py -q
```

Expected: PASS.

- [ ] **Step 2: Run runtime integration tests**

Run:

```bash
pytest tests/integration/test_runtime_llm_api.py -q
```

Expected: PASS.

- [ ] **Step 3: Run existing Dataset/preview integration tests**

Run:

```bash
pytest tests/integration/test_m6_datasets.py -q
```

Expected: PASS.

- [ ] **Step 4: Run frontend tests**

Run:

```bash
npm --prefix frontend run test -- --run
```

Expected: PASS.

- [ ] **Step 5: Run frontend lint**

Run:

```bash
npm --prefix frontend run lint
```

Expected: PASS with no lint errors.

- [ ] **Step 6: Run Python lint and type checks for touched backend files**

Run:

```bash
ruff check adacascade/local_llm_runtime.py adacascade/llm_client.py adacascade/api/routes/runtime.py adacascade/api/app.py tests/unit/test_local_llm_runtime.py tests/unit/test_llm_client_local_tracking.py tests/integration/test_runtime_llm_api.py
mypy --strict adacascade/local_llm_runtime.py adacascade/llm_client.py adacascade/api/routes/runtime.py adacascade/api/app.py
```

Expected: PASS.

- [ ] **Step 7: Manual smoke test without local vLLM running**

Run backend using the usual local demo command with `--workers 1` and main data paths. Start frontend on port `6006` with same-origin proxy mode. Do not manually start vLLM.

Open:

```text
http://localhost:6006/
```

Expected:

- Page loads.
- API model is selectable.
- GPU memory is not occupied by vLLM before Local is selected.

- [ ] **Step 8: Manual local startup and release test**

In the browser:

1. Click **Local model**.
2. Confirm the UI shows `Starting local model…` while the backend starts vLLM.
3. Wait until Local is selected.
4. Run a small task that reaches matcher LLM verification.
5. Click **API model**.
6. Confirm vLLM process stops and GPU memory is released.

Expected:

- `/runtime/llm` reports `local_status=ready` after local startup.
- `/runtime/llm` reports `local_status=stopped` after switching back to API.
- `data/logs/vllm.log` contains vLLM startup output and no secrets.

- [ ] **Step 9: Commit verification note if any docs changed during verification**

If manual verification reveals a documentation correction, update the relevant docs and commit:

```bash
git add deploy/README.md .env.example
git commit -m "docs(runtime): clarify managed vllm verification"
```

If no docs changed, do not create a commit in this step.

---

## Self-review checklist

- Spec coverage:
  - Runtime status fields are covered by Tasks 3, 6, and 7.
  - Backend-managed startup and shutdown are covered by Tasks 2, 3, and 4.
  - Idle timeout is covered by Tasks 1, 2, and 4.
  - Local request accounting is covered by Task 5.
  - Frontend startup/shutdown UI and polling are covered by Tasks 6 and 7.
  - Documentation and manual checks are covered by Tasks 8 and 9.
- Placeholder scan:
  - The plan contains no `TBD`, no incomplete implementation sections, and no vague test-only instructions.
- Type consistency:
  - `LocalRuntimeStatus`, `LocalRuntimeSnapshot`, `LocalLlmRuntimeManager`, `local_status`, `local_ready`, and `local_last_error` are used consistently across backend and frontend tasks.
- Scope guardrails:
  - The plan does not add external queues or workers.
  - The plan does not change algorithms or prompt schemas.
  - The plan preserves single-worker process-local runtime management.
