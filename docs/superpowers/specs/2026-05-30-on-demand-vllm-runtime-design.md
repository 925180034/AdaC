# On-Demand Local vLLM Runtime Design

## Goal

AdaCascade should not keep a local vLLM process resident on GPU when the user is not actively using the local model. The runtime switcher should keep the existing Local/API model choice, but Local should become an on-demand managed resource: start when needed, report readiness clearly, and stop automatically when no longer needed.

This design is limited to vLLM lifecycle management. It does not change matching algorithms, prompt formats, JSON Schema/Pydantic LLM validation, or the single-worker FastAPI constraint.

## Current behavior

- `scripts/start_llm.sh` starts vLLM manually on port `8000`.
- `adacascade.llm_runtime` stores only the process-local active backend: `local` or `api`.
- `PUT /runtime/llm` switches the active backend but does not start or stop vLLM.
- If vLLM is manually started, it keeps occupying GPU memory until the operator stops it.

## Recommended approach

FastAPI owns the lifecycle of vLLM processes that AdaCascade starts. The backend should expose local runtime status, start local vLLM when the user switches to Local, stop it when the user switches back to API, and stop it after an idle timeout.

The design intentionally avoids external workers or queues. Runtime state remains process-local, so FastAPI must continue to run with one worker.

## Runtime state model

Extend the safe runtime response with local vLLM status:

```json
{
  "backend": "api",
  "base_url": "https://api.deepseek.com/v1",
  "model": "deepseek-v4-flash",
  "api_key_configured": true,
  "local_status": "stopped",
  "local_ready": false,
  "local_last_error": null
}
```

`local_status` values:

- `stopped`: no managed local vLLM process is running.
- `starting`: AdaCascade is starting local vLLM and waiting for readiness.
- `ready`: local vLLM responds successfully to the OpenAI-compatible models endpoint.
- `stopping`: AdaCascade is terminating a managed local vLLM process.
- `error`: startup or health checking failed; `local_last_error` contains a safe summary.

## Backend component boundaries

Add a focused local runtime manager module, for example `adacascade/local_llm_runtime.py`.

Responsibilities:

- Track the managed vLLM subprocess handle.
- Serialize start/stop operations with an async lock.
- Check readiness using `LLM_LOCAL_BASE_URL` plus `/models`.
- Start vLLM via a configurable command that defaults to `scripts/start_llm.sh`.
- Write vLLM stdout/stderr to a log file under `data/logs/vllm.log`.
- Track `last_used_at` and active local request count for idle shutdown.
- Stop only the process it started; do not kill unrelated user-managed vLLM processes.

`adacascade.llm_runtime` should remain responsible for active backend selection and request configuration. The local runtime manager should handle process lifecycle only.

## Switching to Local model

When the frontend sends:

```http
PUT /runtime/llm
{"backend":"local"}
```

The backend should:

1. Acquire the local runtime manager lock.
2. Check whether `LLM_LOCAL_BASE_URL` is already ready.
3. If ready, set active backend to `local` and report `local_status=ready`.
4. If not ready and no managed process exists, start vLLM with the configured command.
5. Poll the models endpoint until ready or until `VLLM_STARTUP_TIMEOUT_SECONDS` expires.
6. If ready, set active backend to `local`.
7. If startup times out or the process exits early, keep or switch the active backend to `api`, set `local_status=error`, and return an appropriate API error or status payload.

The UI should not show Local as selected until the backend reports Local is ready.

## Switching to API model

When the frontend sends:

```http
PUT /runtime/llm
{"backend":"api"}
```

The backend should:

1. Set active backend to `api`.
2. If AdaCascade started a managed vLLM process, begin graceful shutdown.
3. Send `SIGTERM` and wait for a short grace period.
4. If the process does not exit, send `SIGKILL`.
5. Set `local_status=stopped` after termination.

If the local vLLM endpoint is ready but was not started by AdaCascade, the backend may report readiness but must not terminate that external process.

## Idle shutdown

Add configuration:

```env
VLLM_IDLE_TIMEOUT_SECONDS=900
VLLM_STARTUP_TIMEOUT_SECONDS=240
VLLM_SHUTDOWN_GRACE_SECONDS=10
VLLM_LOG_PATH=/root/AdaC/data/logs/vllm.log
VLLM_START_COMMAND=bash scripts/start_llm.sh
```

Default idle timeout should be 15 minutes. This balances GPU release with avoiding repeated cold starts during demos.

On FastAPI startup, start a lightweight idle monitor task. It should periodically stop managed vLLM when all of these are true:

- managed vLLM is running;
- no local LLM request is active;
- `last_used_at` is older than `VLLM_IDLE_TIMEOUT_SECONDS`; and
- either active backend is not `local`, or local backend has been idle beyond the timeout.

## LLM request accounting

Wrap local LLM calls so the manager can track usage:

- Before an LLM request using local backend: increment active local request count.
- After completion or error: decrement active local request count and update `last_used_at`.

The manager must never stop vLLM while active local requests are in progress.

## Frontend behavior

Keep the existing Local/API segmented control, but make statuses explicit:

- When switching to Local, show `Starting local model…` and disable both runtime buttons.
- If Local becomes ready, mark Local selected.
- If startup fails, keep API selected and show a runtime error.
- When switching to API, mark API selected and allow the backend to stop managed vLLM.

The frontend should poll or refetch `/runtime/llm` while `local_status` is `starting` or `stopping`.

## Error handling

- Startup timeout should return a safe message such as `Local vLLM startup timed out`.
- Early process exit should return `Local vLLM exited before becoming ready`.
- Logs should point to `VLLM_LOG_PATH` but must not expose secrets.
- If the local endpoint is ready but externally managed, report `local_ready=true` without claiming the process is managed.

## Testing strategy

Backend tests:

- `PUT /runtime/llm` with `local` starts a mocked managed process when local endpoint is unavailable.
- Runtime switches to local only after readiness succeeds.
- Startup timeout does not leave backend selected as local.
- `PUT /runtime/llm` with `api` stops only a managed process.
- Idle monitor stops a managed process after timeout and never stops while active local requests exist.
- Runtime info includes `local_status`, `local_ready`, and `local_last_error`.

Frontend tests:

- Runtime toolbar shows pending text while Local is starting.
- Runtime controls are disabled during Local startup/shutdown.
- Startup failure preserves API selection and displays the runtime error.
- Runtime info refetches while local status is transitional.

Manual checks:

- Start FastAPI without starting vLLM; GPU memory should stay free.
- Click Local model; vLLM should start and become ready.
- Run a local-model task successfully.
- Click API model; vLLM should stop and release GPU memory.
- Leave Local idle beyond timeout; vLLM should stop automatically.

## Scope guardrails

- Do not introduce Celery, RabbitMQ, Kafka, or another external worker.
- Do not change algorithm defaults or prompt schemas.
- Do not change the OpenAI-compatible request path used by business logic.
- Do not kill user-managed processes that AdaCascade did not start.
- Do not support multi-worker FastAPI for this runtime manager in this iteration.
