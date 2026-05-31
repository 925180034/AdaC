"""Managed local vLLM runtime lifecycle."""

from __future__ import annotations

import asyncio
import os
import shlex
import signal
import subprocess
import threading
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
    """Safe local runtime snapshot for API responses."""

    local_status: LocalRuntimeStatus
    local_ready: bool
    local_last_error: str | None


class LocalRuntimeError(RuntimeError):
    """Raised when the managed local vLLM runtime cannot become ready."""


class ProcessLike(Protocol):
    """Subprocess interface used by the runtime manager."""

    def poll(self) -> int | None:
        """Return the process return code, or None while running."""
        ...

    def terminate(self) -> None:
        """Request graceful process termination."""
        ...

    @property
    def pid(self) -> int:
        """Return the process identifier."""
        ...

    def kill(self) -> None:
        """Forcefully stop the process."""
        ...

    def wait(self, timeout: float | None = None) -> int:
        """Wait for process completion."""
        ...


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
        async with httpx.AsyncClient(timeout=2.0, trust_env=False) as client:
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
        self._lifecycle_lock = threading.RLock()
        self._state_lock = threading.RLock()
        self._state = _State(last_used_at=monotonic())

    @classmethod
    def from_settings(cls) -> LocalLlmRuntimeManager:
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
        with self._state_lock:
            self._refresh_state_from_process()
            return self._snapshot_locked()

    async def ensure_ready(self) -> LocalRuntimeSnapshot:
        """Start managed vLLM if needed without blocking the caller's event loop."""
        return await asyncio.to_thread(self.ensure_ready_sync)

    def ensure_ready_sync(self) -> LocalRuntimeSnapshot:
        """Synchronously start managed vLLM if needed and wait until it is ready.

        A single thread lock protects all lifecycle operations across sync callers
        and async callers delegated through ``asyncio.to_thread``. This avoids
        sharing asyncio synchronization primitives across event loops.
        """
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            pass
        else:
            raise RuntimeError(
                "Local LLM sync readiness cannot run inside an active event loop; "
                "use adacascade.llm_client.chat_async() instead."
            )
        with self._lifecycle_lock:
            return asyncio.run(self._ensure_ready_core())

    async def _ensure_ready_core(self) -> LocalRuntimeSnapshot:
        with self._state_lock:
            self._refresh_state_from_process()
        if await self._ready_probe(self.base_url):
            with self._state_lock:
                if self._state.process is None or self._state.process.poll() is not None:
                    self._state.process = None
                    self._state.managed = False
                self._state.status = "ready"
                self._state.last_error = None
                self._state.last_used_at = self._monotonic()
                return self._snapshot_locked()

        with self._state_lock:
            should_start = self._state.process is None or self._state.process.poll() is not None
        if should_start:
            try:
                with self._state_lock:
                    self._start_process()
            except Exception:
                with self._state_lock:
                    self._set_error("Local vLLM failed to start")
                log.exception(
                    "vllm.start_failed",
                    log_path=str(self.log_path),
                    task_id="runtime-manager",
                )
                raise LocalRuntimeError("Local vLLM failed to start") from None

        deadline = self._monotonic() + self.startup_timeout_seconds
        while True:
            with self._state_lock:
                process = self._state.process
                process_exited = process is not None and process.poll() is not None
            if process_exited:
                with self._state_lock:
                    self._set_error("Local vLLM exited before becoming ready")
                raise LocalRuntimeError("Local vLLM exited before becoming ready")
            if await self._ready_probe(self.base_url):
                with self._state_lock:
                    self._state.status = "ready"
                    self._state.last_error = None
                    self._state.last_used_at = self._monotonic()
                    return self._snapshot_locked()
            if self._monotonic() >= deadline:
                await self._stop_managed_locked()
                with self._state_lock:
                    self._set_error("Local vLLM startup timed out")
                raise LocalRuntimeError("Local vLLM startup timed out")
            await self._sleep(self.health_poll_seconds)

    async def stop_managed(self) -> LocalRuntimeSnapshot:
        """Stop only the managed vLLM process started by this manager."""
        return await asyncio.to_thread(self.stop_managed_sync)

    def stop_managed_sync(self) -> LocalRuntimeSnapshot:
        """Synchronously stop only the managed vLLM process started by this manager."""
        with self._lifecycle_lock:
            return asyncio.run(self._stop_managed_locked())

    async def stop_if_idle(self) -> bool:
        """Stop managed vLLM when no local request is active and idle timeout elapsed."""
        return await asyncio.to_thread(self._stop_if_idle_sync)

    def _stop_if_idle_sync(self) -> bool:
        with self._lifecycle_lock:
            with self._state_lock:
                self._refresh_state_from_process()
                if not self._state.managed or self._state.process is None:
                    return False
                if self._state.status != "ready":
                    return False
                if self._state.active_requests > 0:
                    return False
                idle_for = self._monotonic() - self._state.last_used_at
                if idle_for < self.idle_timeout_seconds:
                    return False
            asyncio.run(self._stop_managed_locked())
            return True

    async def idle_monitor_loop(self) -> None:
        """Periodically stop managed vLLM after the configured idle timeout."""
        while True:
            await self._sleep(min(30.0, max(1.0, self.health_poll_seconds)))
            await self.stop_if_idle()

    @contextmanager
    def track_request(self, backend: str) -> Iterator[None]:
        """Track local LLM request activity for idle shutdown safety."""
        if backend != "local":
            yield
            return

        with self._state_lock:
            self._state.active_requests += 1
        try:
            yield
        finally:
            with self._state_lock:
                self._state.active_requests = max(0, self._state.active_requests - 1)
                self._state.last_used_at = self._monotonic()

    def _snapshot_locked(self) -> LocalRuntimeSnapshot:
        return {
            "local_status": self._state.status,
            "local_ready": self._state.status == "ready",
            "local_last_error": self._state.last_error,
        }

    def _start_process(self) -> None:
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        log_file = self.log_path.open("ab")
        command = shlex.split(self.start_command)
        self._state.status = "starting"
        self._state.last_error = None
        try:
            self._state.process = self._popen_factory(
                command,
                cwd=Path(__file__).resolve().parent.parent,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        except Exception:
            log_file.close()
            raise
        log_file.close()
        self._state.managed = True
        self._state.last_used_at = self._monotonic()
        log.info(
            "vllm.start",
            command=self.start_command,
            log_path=str(self.log_path),
            task_id="runtime-manager",
        )

    async def _stop_managed_locked(self) -> LocalRuntimeSnapshot:
        with self._state_lock:
            process = self._state.process
            if not self._state.managed or process is None:
                return self._snapshot_locked()

            if process.poll() is not None:
                self._refresh_state_from_process()
                if self._state.status != "error":
                    self._state = _State(status="stopped", last_used_at=self._monotonic())
                return self._snapshot_locked()

            self._state.status = "stopping"
        process_already_dead = False
        try:
            pgid = os.getpgid(process.pid)
            try:
                os.killpg(pgid, signal.SIGTERM)
            except ProcessLookupError:
                process_already_dead = True
        except ProcessLookupError:
            pgid = None
            try:
                process.terminate()
            except ProcessLookupError:
                process_already_dead = True

        if not process_already_dead:
            try:
                await asyncio.to_thread(process.wait, self.shutdown_grace_seconds)
            except Exception:
                try:
                    if pgid is None:
                        process.kill()
                    else:
                        os.killpg(pgid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                await asyncio.to_thread(process.wait, None)

        with self._state_lock:
            self._state = _State(status="stopped", last_used_at=self._monotonic())
            snapshot = self._snapshot_locked()
        log.info("vllm.stop", task_id="runtime-manager")
        return snapshot

    def _refresh_state_from_process(self) -> None:
        process = self._state.process
        if not self._state.managed or process is None:
            return
        if process.poll() is None:
            return
        if self._state.status == "ready":
            self._set_error("Local vLLM exited unexpectedly after becoming ready")
            return
        if self._state.status == "error":
            return
        self._state = _State(status="stopped", last_used_at=self._monotonic())

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
