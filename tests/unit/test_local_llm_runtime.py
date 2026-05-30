"""Local vLLM process lifecycle manager tests."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import pytest

from adacascade import local_llm_runtime
from adacascade.local_llm_runtime import (
    LocalLlmRuntimeManager,
    LocalRuntimeError,
    _default_ready_probe,
)


_PROCESS_REGISTRY: dict[int, "FakeProcess"] = {}
_PROCESS_GROUP_SIGNALS: list[tuple[int, int]] = []
_NEXT_PID = 12_345


@pytest.fixture(autouse=True)
def isolate_process_group_ops(monkeypatch: pytest.MonkeyPatch) -> list[tuple[int, int]]:
    """Stub process-group syscalls so unit tests cannot signal real processes."""
    global _NEXT_PID

    _PROCESS_REGISTRY.clear()
    _PROCESS_GROUP_SIGNALS.clear()
    _NEXT_PID = 12_345

    def fake_getpgid(pid: int) -> int:
        raise ProcessLookupError(pid)

    def fake_killpg(pgid: int, sig: int) -> None:
        _PROCESS_GROUP_SIGNALS.append((pgid, sig))
        proc = _PROCESS_REGISTRY.get(pgid)
        if proc is None:
            raise ProcessLookupError(pgid)
        if sig == local_llm_runtime.signal.SIGTERM:
            proc.poll_values = [0]
        elif sig == local_llm_runtime.signal.SIGKILL:
            proc.killed = True
            proc.poll_values = [0]

    monkeypatch.setattr(local_llm_runtime.os, "getpgid", fake_getpgid)
    monkeypatch.setattr(local_llm_runtime.os, "killpg", fake_killpg)
    return _PROCESS_GROUP_SIGNALS


class FakeProcess:
    def __init__(
        self,
        *,
        poll_values: list[int | None] | None = None,
        terminate_error: Exception | None = None,
        kill_error: Exception | None = None,
    ) -> None:
        global _NEXT_PID

        self.pid = _NEXT_PID
        _NEXT_PID += 1
        _PROCESS_REGISTRY[self.pid] = self
        self.poll_values = poll_values or [None]
        self.terminate_error = terminate_error
        self.kill_error = kill_error
        self.terminated = False
        self.killed = False
        self.wait_calls = 0

    def poll(self) -> int | None:
        if len(self.poll_values) > 1:
            return self.poll_values.pop(0)
        return self.poll_values[0]

    def terminate(self) -> None:
        if self.terminate_error is not None:
            raise self.terminate_error
        self.terminated = True
        self.poll_values = [0]

    def kill(self) -> None:
        if self.kill_error is not None:
            raise self.kill_error
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


class FakeLogFile:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


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
async def test_ensure_ready_starts_managed_process_in_new_session(tmp_path: Path) -> None:
    popen_kwargs: dict[str, Any] = {}

    def popen_factory(*args: Any, **kwargs: Any) -> FakeProcess:
        popen_kwargs.update(kwargs)
        return FakeProcess()

    runtime = manager(
        tmp_path,
        ready_probe=ProbeSequence([False, True]),
        popen_factory=popen_factory,
    )

    await runtime.ensure_ready()

    assert popen_kwargs["start_new_session"] is True


@pytest.mark.anyio
async def test_ensure_ready_closes_parent_log_handle_after_successful_popen(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log_file = FakeLogFile()

    class FakeLogPath:
        parent = tmp_path

        def open(self, mode: str) -> FakeLogFile:
            assert mode == "ab"
            return log_file

    monkeypatch.setattr(Path, "mkdir", lambda self, parents, exist_ok: None)
    runtime = manager(
        tmp_path,
        ready_probe=ProbeSequence([False]),
        popen_factory=lambda *args, **kwargs: FakeProcess(),
    )
    runtime.log_path = FakeLogPath()

    runtime._start_process()

    assert log_file.closed is True


@pytest.mark.anyio
async def test_ensure_ready_closes_parent_log_handle_when_popen_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log_file = FakeLogFile()

    class FakeLogPath:
        parent = tmp_path

        def open(self, mode: str) -> FakeLogFile:
            assert mode == "ab"
            return log_file

    monkeypatch.setattr(Path, "mkdir", lambda self, parents, exist_ok: None)
    runtime = manager(
        tmp_path,
        ready_probe=ProbeSequence([False]),
        popen_factory=lambda *args, **kwargs: (_ for _ in ()).throw(OSError("boom")),
    )
    runtime.log_path = FakeLogPath()

    with pytest.raises(OSError, match="boom"):
        runtime._start_process()

    assert log_file.closed is True


@pytest.mark.anyio
async def test_ensure_ready_converts_startup_failure_to_safe_runtime_error(
    tmp_path: Path,
) -> None:
    runtime = manager(
        tmp_path,
        ready_probe=ProbeSequence([False]),
        popen_factory=lambda *args, **kwargs: (_ for _ in ()).throw(OSError("sensitive startup failure")),
    )

    with pytest.raises(LocalRuntimeError, match="Local vLLM failed to start"):
        await runtime.ensure_ready()

    snapshot = runtime.snapshot()
    assert snapshot["local_status"] == "error"
    assert snapshot["local_ready"] is False
    assert snapshot["local_last_error"] == "Local vLLM failed to start"


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
async def test_ensure_ready_clears_stale_managed_process_when_external_endpoint_is_ready(
    tmp_path: Path,
) -> None:
    stale_process = FakeProcess(poll_values=[1])
    runtime = manager(tmp_path, ready_probe=ProbeSequence([True]))
    runtime._state.process = stale_process
    runtime._state.managed = True
    runtime._state.status = "ready"

    snapshot = await runtime.ensure_ready()
    stop_snapshot = await runtime.stop_managed()

    assert snapshot == {
        "local_status": "ready",
        "local_ready": True,
        "local_last_error": None,
    }
    assert runtime._state.managed is False
    assert runtime._state.process is None
    assert runtime.snapshot() == {
        "local_status": "ready",
        "local_ready": True,
        "local_last_error": None,
    }
    assert stale_process.terminated is False
    assert stale_process.killed is False
    assert stale_process.wait_calls == 0
    assert stop_snapshot == {
        "local_status": "ready",
        "local_ready": True,
        "local_last_error": None,
    }


@pytest.mark.anyio
async def test_ensure_ready_times_out_and_reports_safe_error(tmp_path: Path) -> None:
    runtime = manager(
        tmp_path,
        ready_probe=ProbeSequence([False]),
        monotonic=monotonic_sequence([0, 1, 2, 4, 6]),
    )

    with pytest.raises(LocalRuntimeError, match="Local vLLM startup timed out"):
        await runtime.ensure_ready()

    snapshot = runtime.snapshot()
    assert snapshot["local_status"] == "error"
    assert snapshot["local_ready"] is False
    assert snapshot["local_last_error"] == "Local vLLM startup timed out"


@pytest.mark.anyio
async def test_ensure_ready_timeout_stops_managed_process_group(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proc = FakeProcess()
    killed_groups: list[tuple[int, int]] = []

    def fake_killpg(pgid: int, sig: int) -> None:
        killed_groups.append((pgid, sig))
        proc.poll_values = [0]

    monkeypatch.setattr(local_llm_runtime.os, "getpgid", lambda pid: pid + 10)
    monkeypatch.setattr(local_llm_runtime.os, "killpg", fake_killpg)
    runtime = manager(
        tmp_path,
        ready_probe=ProbeSequence([False]),
        popen_factory=lambda *args, **kwargs: proc,
        monotonic=monotonic_sequence([0, 1, 2, 4, 5]),
    )

    with pytest.raises(LocalRuntimeError, match="Local vLLM startup timed out"):
        await runtime.ensure_ready()

    assert killed_groups == [(proc.pid + 10, local_llm_runtime.signal.SIGTERM)]
    assert proc.wait_calls == 1
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

    assert _PROCESS_GROUP_SIGNALS == []
    assert proc.terminated is True
    assert snapshot["local_status"] == "stopped"
    assert snapshot["local_ready"] is False


@pytest.mark.anyio
async def test_stop_managed_terminates_managed_process_group(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proc = FakeProcess()
    killed_groups: list[tuple[int, int]] = []

    def fake_killpg(pgid: int, sig: int) -> None:
        killed_groups.append((pgid, sig))
        proc.poll_values = [0]

    monkeypatch.setattr(local_llm_runtime.os, "getpgid", lambda pid: pid + 10)
    monkeypatch.setattr(local_llm_runtime.os, "killpg", fake_killpg)
    runtime = manager(
        tmp_path,
        ready_probe=ProbeSequence([False, True]),
        popen_factory=lambda *args, **kwargs: proc,
    )
    await runtime.ensure_ready()

    await runtime.stop_managed()

    assert killed_groups == [(proc.pid + 10, local_llm_runtime.signal.SIGTERM)]
    assert proc.terminated is False


@pytest.mark.anyio
async def test_stop_managed_treats_already_dead_fallback_process_as_stopped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proc = FakeProcess(terminate_error=ProcessLookupError())
    monkeypatch.setattr(
        local_llm_runtime.os,
        "getpgid",
        lambda pid: (_ for _ in ()).throw(ProcessLookupError()),
    )
    runtime = manager(
        tmp_path,
        ready_probe=ProbeSequence([False, True]),
        popen_factory=lambda *args, **kwargs: proc,
    )
    await runtime.ensure_ready()

    snapshot = await runtime.stop_managed()

    assert snapshot["local_status"] == "stopped"
    assert snapshot["local_ready"] is False


@pytest.mark.anyio
async def test_stop_managed_treats_already_dead_process_group_as_stopped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proc = FakeProcess()
    killpg_calls: list[tuple[int, int]] = []

    def fake_killpg(pgid: int, sig: int) -> None:
        killpg_calls.append((pgid, sig))
        raise ProcessLookupError()

    monkeypatch.setattr(local_llm_runtime.os, "getpgid", lambda pid: pid + 10)
    monkeypatch.setattr(local_llm_runtime.os, "killpg", fake_killpg)
    runtime = manager(
        tmp_path,
        ready_probe=ProbeSequence([False, True]),
        popen_factory=lambda *args, **kwargs: proc,
    )
    await runtime.ensure_ready()

    snapshot = await runtime.stop_managed()

    assert killpg_calls == [(proc.pid + 10, local_llm_runtime.signal.SIGTERM)]
    assert snapshot["local_status"] == "stopped"
    assert snapshot["local_ready"] is False


@pytest.mark.anyio
async def test_stop_managed_skips_signals_for_already_exited_managed_process(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proc = FakeProcess()
    getpgid_calls: list[int] = []

    def fake_getpgid(pid: int) -> int:
        getpgid_calls.append(pid)
        return pid + 10

    def fail_killpg(pgid: int, sig: int) -> None:
        raise AssertionError("killpg should not be called for exited processes")

    monkeypatch.setattr(local_llm_runtime.os, "getpgid", fake_getpgid)
    monkeypatch.setattr(local_llm_runtime.os, "killpg", fail_killpg)
    runtime = manager(
        tmp_path,
        ready_probe=ProbeSequence([False, True]),
        popen_factory=lambda *args, **kwargs: proc,
    )
    await runtime.ensure_ready()
    proc.poll_values = [1]

    snapshot = await runtime.stop_managed()

    assert getpgid_calls == []
    assert proc.terminated is False
    assert proc.wait_calls == 0
    assert snapshot["local_status"] == "error"
    assert snapshot["local_ready"] is False
    assert snapshot["local_last_error"] == "Local vLLM exited unexpectedly after becoming ready"


@pytest.mark.anyio
async def test_stop_managed_ignores_already_dead_process_during_forced_kill(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class StubbornDeadProcess(FakeProcess):
        def terminate(self) -> None:
            self.terminated = True

        def kill(self) -> None:
            self.killed = True
            raise ProcessLookupError()

        def wait(self, timeout: float | None = None) -> int:
            self.wait_calls += 1
            if timeout is not None:
                raise TimeoutError("still running")
            return 0

    proc = StubbornDeadProcess()
    monkeypatch.setattr(
        local_llm_runtime.os,
        "getpgid",
        lambda pid: (_ for _ in ()).throw(ProcessLookupError()),
    )
    runtime = manager(
        tmp_path,
        ready_probe=ProbeSequence([False, True]),
        popen_factory=lambda *args, **kwargs: proc,
    )
    await runtime.ensure_ready()

    snapshot = await runtime.stop_managed()

    assert proc.terminated is True
    assert proc.killed is True
    assert proc.wait_calls == 2
    assert snapshot["local_status"] == "stopped"
    assert snapshot["local_ready"] is False


@pytest.mark.anyio
async def test_startup_timeout_treats_already_dead_fallback_process_as_stopped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proc = FakeProcess(terminate_error=ProcessLookupError())
    monkeypatch.setattr(
        local_llm_runtime.os,
        "getpgid",
        lambda pid: (_ for _ in ()).throw(ProcessLookupError()),
    )
    runtime = manager(
        tmp_path,
        ready_probe=ProbeSequence([False]),
        popen_factory=lambda *args, **kwargs: proc,
        monotonic=monotonic_sequence([0, 1, 2, 4, 5]),
    )

    with pytest.raises(LocalRuntimeError, match="Local vLLM startup timed out"):
        await runtime.ensure_ready()

    snapshot = runtime.snapshot()
    assert snapshot["local_status"] == "error"
    assert snapshot["local_ready"] is False
    assert snapshot["local_last_error"] == "Local vLLM startup timed out"


@pytest.mark.anyio
async def test_lifecycle_logs_include_runtime_manager_task_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[tuple[str, dict[str, Any]]] = []

    class FakeLogger:
        def info(self, event: str, **kwargs: Any) -> None:
            events.append((event, kwargs))

    monkeypatch.setattr(local_llm_runtime, "log", FakeLogger())
    runtime = manager(tmp_path, ready_probe=ProbeSequence([False, True]))

    await runtime.ensure_ready()
    await runtime.stop_managed()

    assert events[0][0] == "vllm.start"
    assert events[0][1]["task_id"] == "runtime-manager"
    assert events[1] == ("vllm.stop", {"task_id": "runtime-manager"})


@pytest.mark.anyio
async def test_stop_managed_waits_without_blocking_event_loop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proc = FakeProcess()
    to_thread_calls: list[tuple[Callable[..., Any], tuple[Any, ...]]] = []

    async def fake_to_thread(func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        to_thread_calls.append((func, args))
        return func(*args, **kwargs)

    monkeypatch.setattr(local_llm_runtime.os, "getpgid", lambda pid: pid + 10)
    monkeypatch.setattr(local_llm_runtime.os, "killpg", lambda pgid, sig: proc.terminate())
    monkeypatch.setattr(local_llm_runtime.asyncio, "to_thread", fake_to_thread)
    runtime = manager(
        tmp_path,
        ready_probe=ProbeSequence([False, True]),
        popen_factory=lambda *args, **kwargs: proc,
    )
    await runtime.ensure_ready()

    await runtime.stop_managed()

    assert to_thread_calls == [(proc.wait, (1,))]


@pytest.mark.anyio
async def test_default_ready_probe_bypasses_environment_proxy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client_kwargs: dict[str, Any] = {}

    class FakeResponse:
        status_code = 200

    class FakeAsyncClient:
        def __init__(self, **kwargs: Any) -> None:
            client_kwargs.update(kwargs)

        async def __aenter__(self) -> FakeAsyncClient:
            return self

        async def __aexit__(self, *args: Any) -> None:
            return None

        async def get(self, url: str) -> FakeResponse:
            assert url == "http://localhost:8000/v1/models"
            return FakeResponse()

    monkeypatch.setattr(local_llm_runtime.httpx, "AsyncClient", FakeAsyncClient)

    ready = await _default_ready_probe("http://localhost:8000/v1")

    assert ready is True
    assert client_kwargs["trust_env"] is False


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
async def test_idle_shutdown_uses_readiness_time_not_manager_construction_time(
    tmp_path: Path,
) -> None:
    proc = FakeProcess()
    runtime = manager(
        tmp_path,
        ready_probe=ProbeSequence([False, False, True]),
        popen_factory=lambda *args, **kwargs: proc,
        monotonic=monotonic_sequence([0, 50, 51, 52, 62, 62, 73]),
    )
    await runtime.ensure_ready()

    stopped_immediately = await runtime.stop_if_idle()

    assert stopped_immediately is False
    assert proc.terminated is False

    stopped_after_timeout = await runtime.stop_if_idle()

    assert stopped_after_timeout is True
    assert proc.terminated is True
    assert runtime.snapshot()["local_status"] == "stopped"


@pytest.mark.anyio
async def test_snapshot_marks_unexpected_exit_after_ready_as_error(tmp_path: Path) -> None:
    proc = FakeProcess()
    runtime = manager(
        tmp_path,
        ready_probe=ProbeSequence([False, True]),
        popen_factory=lambda *args, **kwargs: proc,
    )
    await runtime.ensure_ready()
    proc.poll_values = [1]

    snapshot = runtime.snapshot()

    assert snapshot["local_status"] == "error"
    assert snapshot["local_ready"] is False
    assert snapshot["local_last_error"] == "Local vLLM exited unexpectedly after becoming ready"


@pytest.mark.anyio
async def test_stop_if_idle_does_not_treat_exited_ready_process_as_running(tmp_path: Path) -> None:
    proc = FakeProcess()
    runtime = manager(
        tmp_path,
        ready_probe=ProbeSequence([False, True]),
        popen_factory=lambda *args, **kwargs: proc,
        monotonic=monotonic_sequence([0, 1, 20]),
    )
    await runtime.ensure_ready()
    proc.poll_values = [1]

    stopped = await runtime.stop_if_idle()

    assert stopped is False
    assert runtime.snapshot()["local_status"] == "error"
    assert runtime.snapshot()["local_ready"] is False
    assert proc.terminated is False


@pytest.mark.anyio
async def test_idle_shutdown_stops_managed_process_after_timeout(tmp_path: Path) -> None:
    proc = FakeProcess()
    runtime = manager(
        tmp_path,
        ready_probe=ProbeSequence([False, True]),
        popen_factory=lambda *args, **kwargs: proc,
        monotonic=monotonic_sequence([0, 1, 20, 20, 31]),
    )
    await runtime.ensure_ready()

    stopped = await runtime.stop_if_idle()

    assert stopped is True
    assert proc.terminated is True
    assert runtime.snapshot()["local_status"] == "stopped"
