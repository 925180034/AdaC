# M3.5 Frontend Demo Workbench Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a polished local AdaCascade demo frontend that can launch discovery, matching, and integrated tasks, stream Agent/Layer progress, and visualize results as an interactive research workbench.

**Architecture:** Add a separate React + Vite + TypeScript app under `frontend/` and keep the existing FastAPI backend as the execution service. Add a minimal in-process task event bus and `GET /tasks/{task_id}/events` SSE endpoint so the frontend can show real-time progress without introducing Redis, Celery, or a microservice split.

**Tech Stack:** React, Vite, TypeScript, React Query, Zustand, React Flow, @microsoft/fetch-event-source, Vitest, React Testing Library, Playwright, FastAPI SSE via `StreamingResponse`.

---

## Visual Direction

Use a dark research-control-room aesthetic, not a generic admin template.

- Tone: refined industrial research cockpit.
- Background: near-black blue graphite with subtle radial glows and thin circuit/grid lines.
- Accent colors:
  - cyan-blue for query/source inputs,
  - green for candidate/target tables,
  - violet for mappings,
  - amber for degraded states,
  - red for failed states.
- Typography: avoid generic default-looking UI. Use a deliberate pairing in CSS variables, for example a technical display face for headings and a readable sans for dense tables. If external fonts are unavailable, define fallbacks but still tune letter spacing, weight, and numeric alignment.
- Composition: three-column cockpit with a strong central graph, glass panels, thin luminous borders, compact metadata chips, and animated status pulses.
- Motion: restrained but intentional. Use staggered panel entrance, running-agent shimmer, graph edge pulse during active task, and hover states for selectable nodes/rows.
- Accessibility: all status colors must also have text labels/icons; keyboard focus must be visible; tables and buttons must remain readable on dark backgrounds.

---

## File Map

### Backend files to create or modify

- Create: `adacascade/api/events.py`
  - In-process task event bus.
  - Task event type helpers.
  - SSE stream generator.
- Modify: `adacascade/api/routes/tasks.py`
  - Add `GET /tasks/{task_id}/events`.
  - Tenant-scope the SSE endpoint using the same auth/tenant model as `GET /tasks/{task_id}`.
- Modify: `adacascade/api/routes/operations.py`
  - Emit `task_created`, `agent_started`, `agent_completed`, `agent_degraded`, `agent_failed`, and `task_completed` events around the existing graph task flow.
- Modify: `adacascade/agents/retrieval/__init__.py`
  - Optionally emit Retrieval L1/L2/L3 layer events if the first backend task adds event hook plumbing into state.
  - If keeping the first backend slice minimal, preserve existing behavior and let `operations.py` emit coarse fallback timeline events.
- Test: `tests/integration/test_m3_5_sse.py`
  - Verify the SSE endpoint streams task events for a mocked graph flow.
  - Verify tenant isolation on the SSE endpoint.

### Frontend files to create

- Create: `frontend/package.json`
- Create: `frontend/index.html`
- Create: `frontend/vite.config.ts`
- Create: `frontend/tsconfig.json`
- Create: `frontend/tsconfig.node.json`
- Create: `frontend/.eslintrc.cjs`
- Create: `frontend/playwright.config.ts`
- Create: `frontend/src/main.tsx`
- Create: `frontend/src/app/App.tsx`
- Create: `frontend/src/app/App.test.tsx`
- Create: `frontend/src/api/client.ts`
- Create: `frontend/src/api/tables.ts`
- Create: `frontend/src/api/tasks.ts`
- Create: `frontend/src/api/events.ts`
- Create: `frontend/src/features/tasks/taskTypes.ts`
- Create: `frontend/src/features/tasks/taskStore.ts`
- Create: `frontend/src/features/tasks/timeline.ts`
- Create: `frontend/src/features/graph/graphTypes.ts`
- Create: `frontend/src/features/graph/graphModel.ts`
- Create: `frontend/src/features/graph/ResultGraph.tsx`
- Create: `frontend/src/features/workspace/WorkspacePage.tsx`
- Create: `frontend/src/features/workspace/TaskControlPanel.tsx`
- Create: `frontend/src/features/workspace/ResultWorkspace.tsx`
- Create: `frontend/src/features/workspace/AgentTracePanel.tsx`
- Create: `frontend/src/components/StatusBadge.tsx`
- Create: `frontend/src/components/ScoreBar.tsx`
- Create: `frontend/src/components/EmptyState.tsx`
- Create: `frontend/src/components/JsonViewer.tsx`
- Create: `frontend/src/styles/globals.css`
- Create: `frontend/src/test/setup.ts`
- Create: `frontend/src/features/graph/graphModel.test.ts`
- Create: `frontend/src/features/tasks/timeline.test.ts`
- Create: `frontend/src/features/workspace/TaskControlPanel.test.tsx`
- Create: `frontend/e2e/workspace.spec.ts`

### Documentation and tracking files

- Modify: `TODO.md`
  - Mark M3.5 items complete as implementation tasks land.
- Create or modify: `frontend/.env.example`
  - Document local-only demo env vars.

---

## Task 1: Backend task event bus and SSE endpoint

**Files:**
- Create: `adacascade/api/events.py`
- Modify: `adacascade/api/routes/tasks.py`
- Test: `tests/integration/test_m3_5_sse.py`

- [ ] **Step 1: Write failing SSE integration tests**

Create `tests/integration/test_m3_5_sse.py` with:

```python
"""M3.5 SSE task event endpoint tests."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from adacascade.api.events import emit_task_event
from adacascade.db.models import IntegrationTask
from adacascade.db.session import get_session

AUTH_HEADERS = {"Authorization": "Bearer dev-local-token"}
TENANT_A_HEADERS = {**AUTH_HEADERS, "X-Tenant-Id": "tenant-a"}
TENANT_B_HEADERS = {**AUTH_HEADERS, "X-Tenant-Id": "tenant-b"}


@pytest.fixture(scope="module")
def client() -> TestClient:
    mock_qdrant = MagicMock()
    mock_qdrant.delete_table = AsyncMock()
    raw_qdrant_mock = AsyncMock()
    with (
        patch("qdrant_client.AsyncQdrantClient", return_value=raw_qdrant_mock),
        patch("adacascade.api.app.AdacQdrantClient", return_value=mock_qdrant),
        patch("adacascade.api.app.reconcile_orphan_ingests", new=AsyncMock(return_value=0)),
    ):
        from adacascade.api.app import app

        with TestClient(app, raise_server_exceptions=False) as c:
            _seed_task("sse-task-a", "tenant-a")
            yield c


def _seed_task(task_id: str, tenant_id: str) -> None:
    now = datetime.now(timezone.utc)
    with get_session() as db:
        existing = db.query(IntegrationTask).filter_by(task_id=task_id).first()
        if existing is None:
            db.add(
                IntegrationTask(
                    task_id=task_id,
                    tenant_id=tenant_id,
                    task_type="DISCOVER_ONLY",
                    query_table_id=None,
                    target_table_id=None,
                    plan_config="{}",
                    status="RUNNING",
                    submitted_at=now,
                    finished_at=None,
                    error_message=None,
                    artifacts_dir=None,
                )
            )


def test_sse_endpoint_requires_same_tenant(client: TestClient) -> None:
    hidden = client.get("/tasks/sse-task-a/events", headers=TENANT_B_HEADERS)
    assert hidden.status_code == 404


def test_sse_endpoint_streams_task_event(client: TestClient) -> None:
    asyncio.run(
        emit_task_event(
            "sse-task-a",
            {
                "type": "agent_started",
                "agent": "Retrieval",
                "layer": "L1",
                "message": "Retrieval L1 started",
            },
        )
    )
    asyncio.run(emit_task_event("sse-task-a", {"type": "task_completed", "status": "SUCCESS"}))

    with client.stream("GET", "/tasks/sse-task-a/events", headers=TENANT_A_HEADERS) as resp:
        assert resp.status_code == 200
        body = "".join(resp.iter_text())

    assert "event: agent_started" in body
    assert '"agent":"Retrieval"' in body
    assert "event: task_completed" in body
```

- [ ] **Step 2: Run the failing SSE test**

Run:

```bash
pytest tests/integration/test_m3_5_sse.py -v
```

Expected: FAIL because `adacascade.api.events` and `/tasks/{task_id}/events` do not exist.

- [ ] **Step 3: Implement event bus**

Create `adacascade/api/events.py`:

```python
"""In-process task event bus for local SSE progress streaming."""

from __future__ import annotations

import asyncio
import json
from collections import defaultdict, deque
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from typing import Any

TaskEvent = dict[str, Any]

_HISTORY_LIMIT = 200
_history: dict[str, deque[TaskEvent]] = defaultdict(lambda: deque(maxlen=_HISTORY_LIMIT))
_subscribers: dict[str, set[asyncio.Queue[TaskEvent]]] = defaultdict(set)


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


async def emit_task_event(task_id: str, event: TaskEvent) -> None:
    """Publish one task event to history and active subscribers."""
    payload = {"task_id": task_id, "timestamp": _timestamp(), **event}
    _history[task_id].append(payload)
    for queue in list(_subscribers.get(task_id, set())):
        await queue.put(payload)


def _format_sse(event: TaskEvent) -> str:
    event_type = str(event.get("type", "message"))
    data = json.dumps(event, ensure_ascii=False, separators=(",", ":"))
    return f"event: {event_type}\ndata: {data}\n\n"


async def stream_task_events(task_id: str) -> AsyncIterator[str]:
    """Yield existing and live task events as SSE frames."""
    queue: asyncio.Queue[TaskEvent] = asyncio.Queue()
    _subscribers[task_id].add(queue)
    try:
        for event in list(_history.get(task_id, [])):
            yield _format_sse(event)
            if event.get("type") == "task_completed":
                return
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=10.0)
            except TimeoutError:
                yield _format_sse(
                    {
                        "task_id": task_id,
                        "type": "heartbeat",
                        "timestamp": _timestamp(),
                    }
                )
                continue
            yield _format_sse(event)
            if event.get("type") == "task_completed":
                return
    finally:
        _subscribers[task_id].discard(queue)
        if not _subscribers[task_id]:
            _subscribers.pop(task_id, None)
```

- [ ] **Step 4: Add SSE endpoint**

Modify `adacascade/api/routes/tasks.py` imports:

```python
from fastapi.responses import StreamingResponse

from adacascade.api.events import stream_task_events
```

Add below `get_task`:

```python
@router.get("/{task_id}/events")
async def get_task_events(
    task_id: str, request: Request, db: Session = Depends(get_db)
) -> StreamingResponse:
    """Stream live task progress events for the authenticated tenant."""
    task = db.query(IntegrationTask).filter_by(task_id=task_id).first()
    if task is None or task.tenant_id != get_tenant_id(request):
        raise HTTPException(status_code=404, detail="Task not found")
    return StreamingResponse(
        stream_task_events(task_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
```

- [ ] **Step 5: Run the SSE test**

Run:

```bash
pytest tests/integration/test_m3_5_sse.py -v
```

Expected: PASS.

- [ ] **Step 6: Run existing integration tests**

Run:

```bash
pytest tests/integration/ -v
```

Expected: all integration tests pass.

- [ ] **Step 7: Commit backend SSE endpoint**

```bash
git add adacascade/api/events.py adacascade/api/routes/tasks.py tests/integration/test_m3_5_sse.py
git commit -m "feat(m3.5): add task event SSE endpoint"
```

---

## Task 2: Backend task lifecycle event emission

**Files:**
- Modify: `adacascade/api/routes/operations.py`
- Test: `tests/integration/test_m3_5_sse.py`

- [ ] **Step 1: Add a failing operation SSE test**

Append to `tests/integration/test_m3_5_sse.py`:

```python
def test_operation_emits_task_lifecycle_events(client: TestClient) -> None:
    from adacascade.api.app import app

    class FakeGraph:
        async def ainvoke(self, state: dict[str, object], config: dict[str, object]) -> dict[str, object]:
            return {**state, "ranking": [], "final_mappings": []}

    app.state.graph = FakeGraph()
    response = client.post(
        "/discover",
        json={"query_table_id": "sse-query"},
        headers=TENANT_A_HEADERS,
    )
    assert response.status_code == 200, response.text
    task_id = response.json()["task_id"]

    with client.stream("GET", f"/tasks/{task_id}/events", headers=TENANT_A_HEADERS) as stream:
        body = "".join(stream.iter_text())

    assert "event: task_created" in body
    assert "event: agent_started" in body
    assert "event: agent_completed" in body
    assert "event: task_completed" in body
```

- [ ] **Step 2: Run the failing lifecycle test**

Run:

```bash
pytest tests/integration/test_m3_5_sse.py::test_operation_emits_task_lifecycle_events -v
```

Expected: FAIL because operation routes do not emit lifecycle events yet.

- [ ] **Step 3: Emit lifecycle events in operation runner**

Modify `adacascade/api/routes/operations.py` imports:

```python
from adacascade.api.events import emit_task_event
```

Inside `_run_task`, after `task = _create_task(...)`, add:

```python
    await emit_task_event(
        task.task_id,
        {
            "type": "task_created",
            "status": "RUNNING",
            "message": f"{task_type} task created",
        },
    )
```

Before `state = await request.app.state.graph.ainvoke(...)`, add:

```python
        await emit_task_event(
            task.task_id,
            {
                "type": "agent_started",
                "agent": "Planner",
                "message": "AdaCascade graph started",
            },
        )
```

After `_persist_success(db, task, state)`, add before returning:

```python
        await emit_task_event(
            task.task_id,
            {
                "type": "agent_completed",
                "agent": "Matcher" if task_type != "DISCOVER_ONLY" else "Retrieval",
                "status": "SUCCESS",
                "message": "AdaCascade graph completed",
                "output_size": len(state.get("final_mappings", []))
                if task_type != "DISCOVER_ONLY"
                else len(state.get("ranking", [])),
            },
        )
        await emit_task_event(
            task.task_id,
            {
                "type": "task_completed",
                "status": task.status,
                "message": "Task completed successfully",
            },
        )
```

Inside `except Exception as exc`, after `_persist_failure(task, exc)`, add:

```python
        await emit_task_event(
            task.task_id,
            {
                "type": "agent_failed",
                "status": "FAILED",
                "message": str(exc),
            },
        )
        await emit_task_event(
            task.task_id,
            {
                "type": "task_completed",
                "status": "FAILED",
                "message": str(exc),
            },
        )
```

- [ ] **Step 4: Run lifecycle test**

Run:

```bash
pytest tests/integration/test_m3_5_sse.py::test_operation_emits_task_lifecycle_events -v
```

Expected: PASS.

- [ ] **Step 5: Run integration tests**

Run:

```bash
pytest tests/integration/ -v
```

Expected: PASS.

- [ ] **Step 6: Commit lifecycle events**

```bash
git add adacascade/api/routes/operations.py tests/integration/test_m3_5_sse.py
git commit -m "feat(m3.5): emit task lifecycle events"
```

---

## Task 3: Frontend scaffold and local demo configuration

**Files:**
- Create frontend scaffold files listed in File Map.
- Test: `frontend/src/app/App.test.tsx`

- [ ] **Step 1: Create frontend package files**

Create `frontend/package.json`:

```json
{
  "name": "adacascade-demo-frontend",
  "version": "0.1.0",
  "private": true,
  "type": "module",
  "scripts": {
    "dev": "vite --host 0.0.0.0 --port 5173",
    "lint": "eslint .",
    "test": "vitest run",
    "test:watch": "vitest",
    "test:e2e": "playwright test",
    "build": "tsc -b && vite build",
    "preview": "vite preview --host 0.0.0.0 --port 5173"
  },
  "dependencies": {
    "@microsoft/fetch-event-source": "^2.0.1",
    "@tanstack/react-query": "^5.59.0",
    "dagre": "^0.8.5",
    "lucide-react": "^0.468.0",
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "reactflow": "^11.11.4",
    "zustand": "^5.0.1"
  },
  "devDependencies": {
    "@playwright/test": "^1.49.0",
    "@testing-library/jest-dom": "^6.6.3",
    "@testing-library/react": "^16.1.0",
    "@testing-library/user-event": "^14.5.2",
    "@vitejs/plugin-react": "^4.3.2",
    "@types/dagre": "^0.7.52",
    "@types/node": "^22.10.2",
    "@types/react": "^18.3.12",
    "@types/react-dom": "^18.3.1",
    "@typescript-eslint/eslint-plugin": "^8.18.0",
    "@typescript-eslint/parser": "^8.18.0",
    "eslint": "^8.57.1",
    "eslint-plugin-react-hooks": "^5.1.0",
    "eslint-plugin-react-refresh": "^0.4.16",
    "jsdom": "^25.0.1",
    "typescript": "^5.7.2",
    "vite": "^6.0.3",
    "vitest": "^2.1.8"
  }
}
```

Create `frontend/.env.example`:

```text
VITE_API_BASE_URL=http://localhost:8080
VITE_API_KEY=dev-local-token
VITE_DEFAULT_TENANT_ID=default
```

- [ ] **Step 2: Create Vite TypeScript config**

Create `frontend/tsconfig.json`:

```json
{
  "compilerOptions": {
    "target": "ES2020",
    "useDefineForClassFields": true,
    "lib": ["DOM", "DOM.Iterable", "ES2020"],
    "allowJs": false,
    "skipLibCheck": true,
    "esModuleInterop": true,
    "allowSyntheticDefaultImports": true,
    "strict": true,
    "forceConsistentCasingInFileNames": true,
    "module": "ESNext",
    "moduleResolution": "Node",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true,
    "jsx": "react-jsx",
    "types": ["vitest/globals", "@testing-library/jest-dom"]
  },
  "include": ["src"],
  "references": [{ "path": "./tsconfig.node.json" }]
}
```

Create `frontend/tsconfig.node.json`:

```json
{
  "compilerOptions": {
    "composite": true,
    "skipLibCheck": true,
    "module": "ESNext",
    "moduleResolution": "Node",
    "allowSyntheticDefaultImports": true,
    "strict": true
  },
  "include": ["vite.config.ts", "playwright.config.ts"]
}
```

Create `frontend/vite.config.ts`:

```ts
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    setupFiles: './src/test/setup.ts',
    globals: true,
  },
})
```

- [ ] **Step 3: Create lint and Playwright config**

Create `frontend/.eslintrc.cjs`:

```js
module.exports = {
  root: true,
  env: { browser: true, es2020: true },
  extends: ['eslint:recommended', 'plugin:@typescript-eslint/recommended'],
  ignorePatterns: ['dist', '.eslintrc.cjs'],
  parser: '@typescript-eslint/parser',
  parserOptions: { ecmaVersion: 'latest', sourceType: 'module' },
  plugins: ['react-hooks', 'react-refresh', '@typescript-eslint'],
  rules: {
    'react-hooks/rules-of-hooks': 'error',
    'react-hooks/exhaustive-deps': 'warn',
    'react-refresh/only-export-components': ['warn', { allowConstantExport: true }],
  },
}
```

Create `frontend/playwright.config.ts`:

```ts
import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  retries: 0,
  use: {
    baseURL: 'http://127.0.0.1:5173',
    trace: 'on-first-retry',
  },
  webServer: {
    command: 'npm run dev',
    url: 'http://127.0.0.1:5173',
    reuseExistingServer: true,
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
})
```

- [ ] **Step 4: Create minimal app and test setup**

Create `frontend/index.html`:

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>AdaCascade Workbench</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

Create `frontend/src/test/setup.ts`:

```ts
import '@testing-library/jest-dom/vitest'
```

Create `frontend/src/app/App.tsx`:

```tsx
export function App() {
  return <main>AdaCascade Workbench</main>
}
```

Create `frontend/src/main.tsx`:

```tsx
import React from 'react'
import ReactDOM from 'react-dom/client'
import { App } from './app/App'
import './styles/globals.css'

ReactDOM.createRoot(document.getElementById('root') as HTMLElement).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
```

Create `frontend/src/styles/globals.css`:

```css
:root {
  color: #e6f7ff;
  background: #081018;
  font-family: "Aptos", "Segoe UI", sans-serif;
}

* {
  box-sizing: border-box;
}

body {
  margin: 0;
  min-width: 1280px;
  min-height: 100vh;
  background:
    radial-gradient(circle at top left, rgba(0, 209, 255, 0.18), transparent 32rem),
    radial-gradient(circle at bottom right, rgba(137, 92, 255, 0.16), transparent 34rem),
    #081018;
}

button,
input,
select {
  font: inherit;
}
```

Create `frontend/src/app/App.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { App } from './App'

describe('App', () => {
  it('renders the workbench title', () => {
    render(<App />)
    expect(screen.getByText('AdaCascade Workbench')).toBeInTheDocument()
  })
})
```

- [ ] **Step 5: Install frontend dependencies**

Run:

```bash
cd frontend && npm install
```

Expected: `frontend/package-lock.json` is created.

- [ ] **Step 6: Run scaffold checks**

Run:

```bash
cd frontend && npm run test && npm run build
```

Expected: tests pass and Vite build succeeds.

- [ ] **Step 7: Commit scaffold**

```bash
git add frontend
git commit -m "feat(m3.5): scaffold demo frontend"
```

---

## Task 4: Frontend API types and clients

**Files:**
- Create: `frontend/src/features/tasks/taskTypes.ts`
- Create: `frontend/src/api/client.ts`
- Create: `frontend/src/api/tables.ts`
- Create: `frontend/src/api/tasks.ts`
- Create: `frontend/src/api/events.ts`
- Test: `frontend/src/api/client.test.ts`

- [ ] **Step 1: Define backend DTO and frontend domain types**

Create `frontend/src/features/tasks/taskTypes.ts`:

```ts
export type TaskMode = 'discover' | 'match' | 'integrate'

export type TableSummary = {
  table_id: string
  tenant_id: string
  table_name: string
  row_count: number | null
  col_count: number | null
  status: string
  source_system?: string
}

export type DiscoveryRanking = {
  rank: number
  candidate_table: string
  score: number
  layer_scores: Record<string, number> | null
}

export type ColumnMapping = {
  mapping_id: string
  src_column_id: string
  tgt_column_id: string
  scenario: 'SMD' | 'SSD' | 'SLD'
  confidence: number
  is_matched: boolean
  reasoning: string | null
  created_at: string
}

export type AgentTraceStep = {
  step_id: number
  agent_name: string
  layer: string | null
  input_size: number | null
  output_size: number | null
  latency_ms: number | null
  llm_tokens: number | null
  recall_loss: number | null
  started_at: string
  finished_at: string | null
}

export type TaskDetail = {
  task_id: string
  tenant_id: string
  task_type: 'INTEGRATE' | 'DISCOVER_ONLY' | 'MATCH_ONLY'
  query_table_id: string | null
  target_table_id: string | null
  status: 'RUNNING' | 'SUCCESS' | 'FAILED'
  submitted_at: string
  finished_at: string | null
  error_message: string | null
  plan_config: Record<string, unknown> | null
  trace: AgentTraceStep[]
  ranking: DiscoveryRanking[]
  mappings: ColumnMapping[]
}

export type TaskEvent = {
  task_id: string
  type:
    | 'task_created'
    | 'agent_started'
    | 'agent_completed'
    | 'agent_degraded'
    | 'agent_failed'
    | 'task_completed'
    | 'heartbeat'
  agent?: 'Planner' | 'Profiling' | 'Retrieval' | 'Matcher'
  layer?: string
  status?: 'PENDING' | 'RUNNING' | 'SUCCESS' | 'FAILED' | 'DEGRADED'
  input_size?: number
  output_size?: number
  latency_ms?: number
  llm_tokens?: number
  message?: string
  reason?: string
  fallback?: string
  timestamp: string
}
```

- [ ] **Step 2: Add API client test**

Create `frontend/src/api/client.test.ts`:

```ts
import { describe, expect, it } from 'vitest'
import { buildHeaders, joinUrl } from './client'

describe('API client helpers', () => {
  it('joins base URL and path without duplicate slash', () => {
    expect(joinUrl('http://localhost:8080/', '/tables')).toBe('http://localhost:8080/tables')
  })

  it('builds auth and tenant headers', () => {
    expect(buildHeaders('tenant-a')).toMatchObject({
      Authorization: 'Bearer dev-local-token',
      'X-Tenant-Id': 'tenant-a',
    })
  })
})
```

- [ ] **Step 3: Implement shared API client**

Create `frontend/src/api/client.ts`:

```ts
const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8080'
const apiKey = import.meta.env.VITE_API_KEY ?? 'dev-local-token'

export function joinUrl(baseUrl: string, path: string) {
  return `${baseUrl.replace(/\/$/, '')}/${path.replace(/^\//, '')}`
}

export function buildHeaders(tenantId: string): Record<string, string> {
  return {
    Authorization: `Bearer ${apiKey}`,
    'X-Tenant-Id': tenantId,
  }
}

export async function apiJson<T>(path: string, tenantId: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(joinUrl(apiBaseUrl, path), {
    ...init,
    headers: {
      ...buildHeaders(tenantId),
      'Content-Type': 'application/json',
      ...(init.headers ?? {}),
    },
  })
  if (!response.ok) {
    const text = await response.text()
    throw new Error(text || `Request failed: ${response.status}`)
  }
  return (await response.json()) as T
}

export const API_BASE_URL = apiBaseUrl
```

- [ ] **Step 4: Implement REST clients**

Create `frontend/src/api/tables.ts`:

```ts
import { apiJson } from './client'
import type { TableSummary } from '../features/tasks/taskTypes'

export type ListTablesResponse = {
  items: TableSummary[]
  total: number
  limit: number
  offset: number
}

export function listTables(tenantId: string) {
  return apiJson<ListTablesResponse>('/tables?status=READY&limit=200', tenantId)
}
```

Create `frontend/src/api/tasks.ts`:

```ts
import { apiJson } from './client'
import type { TaskDetail } from '../features/tasks/taskTypes'

export type StartTaskResponse = {
  task_id: string
  status: string
  state: Record<string, unknown>
}

export function startDiscover(tenantId: string, queryTableId: string) {
  return apiJson<StartTaskResponse>('/discover', tenantId, {
    method: 'POST',
    body: JSON.stringify({ query_table_id: queryTableId }),
  })
}

export function startIntegrate(tenantId: string, queryTableId: string) {
  return apiJson<StartTaskResponse>('/integrate', tenantId, {
    method: 'POST',
    body: JSON.stringify({ query_table_id: queryTableId }),
  })
}

export function startMatch(tenantId: string, sourceTableId: string, targetTableId: string) {
  return apiJson<StartTaskResponse>('/match', tenantId, {
    method: 'POST',
    body: JSON.stringify({ source_table_id: sourceTableId, target_table_id: targetTableId }),
  })
}

export function getTask(tenantId: string, taskId: string) {
  return apiJson<TaskDetail>(`/tasks/${taskId}`, tenantId)
}
```

Create `frontend/src/api/events.ts`:

```ts
import { fetchEventSource } from '@microsoft/fetch-event-source'
import { API_BASE_URL, buildHeaders, joinUrl } from './client'
import type { TaskEvent } from '../features/tasks/taskTypes'

export function subscribeTaskEvents(
  tenantId: string,
  taskId: string,
  onEvent: (event: TaskEvent) => void,
  signal: AbortSignal,
) {
  return fetchEventSource(joinUrl(API_BASE_URL, `/tasks/${taskId}/events`), {
    headers: buildHeaders(tenantId),
    signal,
    onmessage(message) {
      if (!message.data) return
      onEvent(JSON.parse(message.data) as TaskEvent)
    },
  })
}
```

- [ ] **Step 5: Run frontend API tests**

Run:

```bash
cd frontend && npm run test -- client.test.ts
```

Expected: PASS.

- [ ] **Step 6: Commit API clients**

```bash
git add frontend/src/api frontend/src/features/tasks/taskTypes.ts
git commit -m "feat(m3.5): add frontend API clients"
```

---

## Task 5: Graph model conversion

**Files:**
- Create: `frontend/src/features/graph/graphTypes.ts`
- Create: `frontend/src/features/graph/graphModel.ts`
- Test: `frontend/src/features/graph/graphModel.test.ts`

- [ ] **Step 1: Write graph conversion tests**

Create `frontend/src/features/graph/graphModel.test.ts`:

```ts
import { describe, expect, it } from 'vitest'
import { buildTaskGraph } from './graphModel'
import type { TaskDetail } from '../tasks/taskTypes'

const baseTask: TaskDetail = {
  task_id: 'task-1',
  tenant_id: 'default',
  task_type: 'INTEGRATE',
  query_table_id: 'query_table',
  target_table_id: null,
  status: 'SUCCESS',
  submitted_at: '2026-04-27T00:00:00Z',
  finished_at: '2026-04-27T00:00:01Z',
  error_message: null,
  plan_config: {},
  trace: [],
  ranking: [
    { rank: 1, candidate_table: 'candidate_a', score: 0.91, layer_scores: { s1: 0.8, s2: 0.9, s3: 0.95 } },
  ],
  mappings: [
    {
      mapping_id: 'mapping-1',
      src_column_id: 'src_name',
      tgt_column_id: 'tgt_name',
      scenario: 'SMD',
      confidence: 0.88,
      is_matched: true,
      reasoning: 'same semantic column',
      created_at: '2026-04-27T00:00:01Z',
    },
  ],
}

describe('buildTaskGraph', () => {
  it('maps ranking items to table nodes and discovery edges', () => {
    const graph = buildTaskGraph(baseTask)
    expect(graph.nodes).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ id: 'table:query_table', kind: 'query_table' }),
        expect.objectContaining({ id: 'table:candidate_a', kind: 'candidate_table' }),
      ]),
    )
    expect(graph.edges).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ kind: 'discovery', source: 'table:query_table', target: 'table:candidate_a', weight: 0.91 }),
      ]),
    )
  })

  it('maps mappings to column nodes and mapping edges', () => {
    const graph = buildTaskGraph(baseTask)
    expect(graph.nodes).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ id: 'column:src_name', kind: 'source_column' }),
        expect.objectContaining({ id: 'column:tgt_name', kind: 'target_column' }),
      ]),
    )
    expect(graph.edges).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ kind: 'mapping', source: 'column:src_name', target: 'column:tgt_name', scenario: 'SMD' }),
      ]),
    )
  })
})
```

- [ ] **Step 2: Implement graph types**

Create `frontend/src/features/graph/graphTypes.ts`:

```ts
export type GraphNodeKind =
  | 'query_table'
  | 'candidate_table'
  | 'source_table'
  | 'target_table'
  | 'source_column'
  | 'target_column'

export type GraphNode = {
  id: string
  kind: GraphNodeKind
  label: string
  table_id?: string
  column_id?: string
  status?: 'normal' | 'matched' | 'degraded' | 'failed'
  metrics?: Record<string, number | string>
}

export type GraphEdge = {
  id: string
  kind: 'discovery' | 'mapping'
  source: string
  target: string
  label?: string
  weight?: number
  scenario?: 'SMD' | 'SSD' | 'SLD'
  explanation?: string
  metrics?: Record<string, number | string>
}

export type TaskGraph = {
  nodes: GraphNode[]
  edges: GraphEdge[]
}
```

- [ ] **Step 3: Implement graph conversion**

Create `frontend/src/features/graph/graphModel.ts`:

```ts
import type { TaskDetail } from '../tasks/taskTypes'
import type { GraphEdge, GraphNode, TaskGraph } from './graphTypes'

function tableNode(id: string, kind: GraphNode['kind']): GraphNode {
  return { id: `table:${id}`, kind, label: id, table_id: id, status: 'normal' }
}

function columnNode(id: string, kind: GraphNode['kind'], matched: boolean): GraphNode {
  return { id: `column:${id}`, kind, label: id, column_id: id, status: matched ? 'matched' : 'normal' }
}

export function buildTaskGraph(task: TaskDetail): TaskGraph {
  const nodes = new Map<string, GraphNode>()
  const edges: GraphEdge[] = []

  if (task.query_table_id) {
    const kind = task.task_type === 'MATCH_ONLY' ? 'source_table' : 'query_table'
    nodes.set(`table:${task.query_table_id}`, tableNode(task.query_table_id, kind))
  }

  if (task.target_table_id) {
    nodes.set(`table:${task.target_table_id}`, tableNode(task.target_table_id, 'target_table'))
  }

  for (const item of task.ranking) {
    nodes.set(`table:${item.candidate_table}`, tableNode(item.candidate_table, 'candidate_table'))
    if (task.query_table_id) {
      edges.push({
        id: `discovery:${task.query_table_id}:${item.candidate_table}`,
        kind: 'discovery',
        source: `table:${task.query_table_id}`,
        target: `table:${item.candidate_table}`,
        label: `#${item.rank} ${item.score.toFixed(3)}`,
        weight: item.score,
        metrics: item.layer_scores ?? undefined,
      })
    }
  }

  for (const mapping of task.mappings) {
    nodes.set(`column:${mapping.src_column_id}`, columnNode(mapping.src_column_id, 'source_column', mapping.is_matched))
    nodes.set(`column:${mapping.tgt_column_id}`, columnNode(mapping.tgt_column_id, 'target_column', mapping.is_matched))
    edges.push({
      id: `mapping:${mapping.mapping_id}`,
      kind: 'mapping',
      source: `column:${mapping.src_column_id}`,
      target: `column:${mapping.tgt_column_id}`,
      label: mapping.confidence.toFixed(3),
      weight: mapping.confidence,
      scenario: mapping.scenario,
      explanation: mapping.reasoning ?? undefined,
    })
  }

  return { nodes: [...nodes.values()], edges }
}
```

- [ ] **Step 4: Run graph tests**

Run:

```bash
cd frontend && npm run test -- graphModel.test.ts
```

Expected: PASS.

- [ ] **Step 5: Commit graph model**

```bash
git add frontend/src/features/graph
git commit -m "feat(m3.5): map task results to graph data"
```

---

## Task 6: Timeline state model

**Files:**
- Create: `frontend/src/features/tasks/timeline.ts`
- Test: `frontend/src/features/tasks/timeline.test.ts`

- [ ] **Step 1: Write timeline tests**

Create `frontend/src/features/tasks/timeline.test.ts`:

```ts
import { describe, expect, it } from 'vitest'
import { INITIAL_TIMELINE, applyTaskEvent } from './timeline'
import type { TaskEvent } from './taskTypes'

describe('applyTaskEvent', () => {
  it('marks a layer as running then success', () => {
    const started: TaskEvent = {
      task_id: 'task-1',
      type: 'agent_started',
      agent: 'Retrieval',
      layer: 'L1',
      timestamp: '2026-04-27T00:00:00Z',
    }
    const completed: TaskEvent = {
      task_id: 'task-1',
      type: 'agent_completed',
      agent: 'Retrieval',
      layer: 'L1',
      output_size: 80,
      timestamp: '2026-04-27T00:00:01Z',
    }

    const running = applyTaskEvent(INITIAL_TIMELINE, started)
    expect(running['Retrieval:L1'].status).toBe('running')

    const success = applyTaskEvent(running, completed)
    expect(success['Retrieval:L1']).toMatchObject({ status: 'success', output_size: 80 })
  })

  it('marks degraded events as degraded with reason', () => {
    const degraded = applyTaskEvent(INITIAL_TIMELINE, {
      task_id: 'task-1',
      type: 'agent_degraded',
      agent: 'Retrieval',
      layer: 'L2',
      reason: 'qdrant down',
      timestamp: '2026-04-27T00:00:00Z',
    })
    expect(degraded['Retrieval:L2']).toMatchObject({ status: 'degraded', reason: 'qdrant down' })
  })
})
```

- [ ] **Step 2: Implement timeline reducer**

Create `frontend/src/features/tasks/timeline.ts`:

```ts
import type { TaskEvent } from './taskTypes'

export type TimelineStatus = 'pending' | 'running' | 'success' | 'degraded' | 'failed'

export type TimelineNode = {
  id: string
  label: string
  status: TimelineStatus
  input_size?: number
  output_size?: number
  latency_ms?: number
  llm_tokens?: number
  reason?: string
  message?: string
}

export type TimelineState = Record<string, TimelineNode>

const nodes: Array<[string, string]> = [
  ['Planner', 'Planner'],
  ['Profiling', 'Profiling'],
  ['Retrieval:L1', 'Retrieval L1'],
  ['Retrieval:L2', 'Retrieval L2'],
  ['Retrieval:L3', 'Retrieval L3'],
  ['Matcher:filtering', 'Matcher Filtering'],
  ['Matcher:LLM', 'Matcher LLM'],
  ['Matcher:decision', 'Matcher Decision'],
]

export const INITIAL_TIMELINE: TimelineState = Object.fromEntries(
  nodes.map(([id, label]) => [id, { id, label, status: 'pending' as const }]),
)

function eventNodeId(event: TaskEvent): string | null {
  if (!event.agent) return null
  if (event.agent === 'Retrieval' && event.layer) return `Retrieval:${event.layer}`
  if (event.agent === 'Matcher' && event.layer) return `Matcher:${event.layer}`
  return event.agent
}

export function applyTaskEvent(state: TimelineState, event: TaskEvent): TimelineState {
  const id = eventNodeId(event)
  if (!id) return state
  const current = state[id] ?? { id, label: id, status: 'pending' as const }
  const status: TimelineStatus =
    event.type === 'agent_started'
      ? 'running'
      : event.type === 'agent_degraded'
        ? 'degraded'
        : event.type === 'agent_failed'
          ? 'failed'
          : event.type === 'agent_completed'
            ? 'success'
            : current.status

  return {
    ...state,
    [id]: {
      ...current,
      status,
      input_size: event.input_size ?? current.input_size,
      output_size: event.output_size ?? current.output_size,
      latency_ms: event.latency_ms ?? current.latency_ms,
      llm_tokens: event.llm_tokens ?? current.llm_tokens,
      reason: event.reason ?? current.reason,
      message: event.message ?? current.message,
    },
  }
}
```

- [ ] **Step 3: Run timeline tests**

Run:

```bash
cd frontend && npm run test -- timeline.test.ts
```

Expected: PASS.

- [ ] **Step 4: Commit timeline model**

```bash
git add frontend/src/features/tasks/timeline.ts frontend/src/features/tasks/timeline.test.ts
git commit -m "feat(m3.5): add task timeline state model"
```

---

## Task 7: Workspace UI shell and polished visual system

**Files:**
- Modify: `frontend/src/app/App.tsx`
- Create: `frontend/src/features/workspace/WorkspacePage.tsx`
- Create: `frontend/src/features/workspace/TaskControlPanel.tsx`
- Create: `frontend/src/features/workspace/ResultWorkspace.tsx`
- Create: `frontend/src/features/workspace/AgentTracePanel.tsx`
- Create: `frontend/src/components/StatusBadge.tsx`
- Create: `frontend/src/components/EmptyState.tsx`
- Create: `frontend/src/components/ScoreBar.tsx`
- Create: `frontend/src/components/JsonViewer.tsx`
- Modify: `frontend/src/styles/globals.css`
- Test: `frontend/src/features/workspace/TaskControlPanel.test.tsx`

- [ ] **Step 1: Write control panel component test**

Create `frontend/src/features/workspace/TaskControlPanel.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { TaskControlPanel } from './TaskControlPanel'

const tables = [
  { table_id: 'table_a', tenant_id: 'default', table_name: 'Table A', row_count: 10, col_count: 3, status: 'READY' },
  { table_id: 'table_b', tenant_id: 'default', table_name: 'Table B', row_count: 12, col_count: 4, status: 'READY' },
]

describe('TaskControlPanel', () => {
  it('renders mode and table controls', () => {
    render(
      <TaskControlPanel
        tenantId="default"
        mode="discover"
        tables={tables}
        queryTableId="table_a"
        sourceTableId=""
        targetTableId=""
        isRunning={false}
        onModeChange={vi.fn()}
        onQueryTableChange={vi.fn()}
        onSourceTableChange={vi.fn()}
        onTargetTableChange={vi.fn()}
        onRun={vi.fn()}
      />,
    )
    expect(screen.getByText('Task Control')).toBeInTheDocument()
    expect(screen.getByLabelText('Mode')).toBeInTheDocument()
    expect(screen.getByLabelText('Query table')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Run AdaCascade' })).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Implement reusable components**

Create `frontend/src/components/StatusBadge.tsx`:

```tsx
type Props = { status: string }

export function StatusBadge({ status }: Props) {
  return <span className={`status-badge status-${status.toLowerCase()}`}>{status}</span>
}
```

Create `frontend/src/components/ScoreBar.tsx`:

```tsx
type Props = { value: number; label?: string }

export function ScoreBar({ value, label }: Props) {
  const percent = Math.max(0, Math.min(100, value * 100))
  return (
    <div className="score-bar" aria-label={label ?? `Score ${value.toFixed(3)}`}>
      <span style={{ width: `${percent}%` }} />
      <strong>{value.toFixed(3)}</strong>
    </div>
  )
}
```

Create `frontend/src/components/EmptyState.tsx`:

```tsx
type Props = { title: string; body: string }

export function EmptyState({ title, body }: Props) {
  return (
    <div className="empty-state">
      <h3>{title}</h3>
      <p>{body}</p>
    </div>
  )
}
```

Create `frontend/src/components/JsonViewer.tsx`:

```tsx
type Props = { value: unknown }

export function JsonViewer({ value }: Props) {
  return <pre className="json-viewer">{JSON.stringify(value, null, 2)}</pre>
}
```

- [ ] **Step 3: Implement workspace components**

Create `frontend/src/features/workspace/TaskControlPanel.tsx`:

```tsx
import type { TableSummary, TaskMode } from '../tasks/taskTypes'

type Props = {
  tenantId: string
  mode: TaskMode
  tables: TableSummary[]
  queryTableId: string
  sourceTableId: string
  targetTableId: string
  isRunning: boolean
  onModeChange: (mode: TaskMode) => void
  onQueryTableChange: (id: string) => void
  onSourceTableChange: (id: string) => void
  onTargetTableChange: (id: string) => void
  onRun: () => void
}

export function TaskControlPanel(props: Props) {
  const showQuery = props.mode === 'discover' || props.mode === 'integrate'
  const showPair = props.mode === 'match'
  return (
    <aside className="panel control-panel">
      <p className="eyebrow">Tenant · {props.tenantId}</p>
      <h2>Task Control</h2>
      <label>
        Mode
        <select value={props.mode} onChange={(event) => props.onModeChange(event.target.value as TaskMode)}>
          <option value="discover">Data discovery</option>
          <option value="match">Schema matching</option>
          <option value="integrate">Integrated flow</option>
        </select>
      </label>
      {showQuery ? (
        <label>
          Query table
          <select value={props.queryTableId} onChange={(event) => props.onQueryTableChange(event.target.value)}>
            <option value="">Select table</option>
            {props.tables.map((table) => (
              <option key={table.table_id} value={table.table_id}>{table.table_name || table.table_id}</option>
            ))}
          </select>
        </label>
      ) : null}
      {showPair ? (
        <>
          <label>
            Source table
            <select value={props.sourceTableId} onChange={(event) => props.onSourceTableChange(event.target.value)}>
              <option value="">Select source</option>
              {props.tables.map((table) => (
                <option key={table.table_id} value={table.table_id}>{table.table_name || table.table_id}</option>
              ))}
            </select>
          </label>
          <label>
            Target table
            <select value={props.targetTableId} onChange={(event) => props.onTargetTableChange(event.target.value)}>
              <option value="">Select target</option>
              {props.tables.map((table) => (
                <option key={table.table_id} value={table.table_id}>{table.table_name || table.table_id}</option>
              ))}
            </select>
          </label>
        </>
      ) : null}
      <button className="run-button" disabled={props.isRunning} onClick={props.onRun}>
        {props.isRunning ? 'Running…' : 'Run AdaCascade'}
      </button>
    </aside>
  )
}
```

Create `frontend/src/features/workspace/ResultWorkspace.tsx`:

```tsx
import { EmptyState } from '../../components/EmptyState'
import { JsonViewer } from '../../components/JsonViewer'
import { ScoreBar } from '../../components/ScoreBar'
import type { TaskDetail } from '../tasks/taskTypes'

type Props = { task: TaskDetail | null }

export function ResultWorkspace({ task }: Props) {
  if (!task) {
    return <EmptyState title="Awaiting task" body="Select a mode and run AdaCascade to generate graph results." />
  }
  return (
    <section className="panel result-panel">
      <div className="tab-strip"><button>Graph</button><button>Ranking</button><button>Mappings</button><button>Raw JSON</button></div>
      <div className="result-grid">
        <section>
          <h3>Ranking</h3>
          {task.ranking.map((item) => (
            <article className="result-row" key={item.candidate_table}>
              <span>#{item.rank}</span>
              <strong>{item.candidate_table}</strong>
              <ScoreBar value={item.score} />
            </article>
          ))}
        </section>
        <section>
          <h3>Mappings</h3>
          {task.mappings.map((item) => (
            <article className="result-row" key={item.mapping_id}>
              <strong>{item.src_column_id}</strong>
              <span>→</span>
              <strong>{item.tgt_column_id}</strong>
              <ScoreBar value={item.confidence} />
            </article>
          ))}
        </section>
      </div>
      <JsonViewer value={task} />
    </section>
  )
}
```

Create `frontend/src/features/workspace/AgentTracePanel.tsx`:

```tsx
import type { TimelineState } from '../tasks/timeline'

type Props = { timeline: TimelineState; events: string[] }

export function AgentTracePanel({ timeline, events }: Props) {
  return (
    <aside className="panel trace-panel">
      <p className="eyebrow">Live Trace</p>
      <h2>Agent Timeline</h2>
      <div className="timeline-list">
        {Object.values(timeline).map((node) => (
          <article className={`timeline-node timeline-${node.status}`} key={node.id}>
            <span className="timeline-dot" />
            <div>
              <strong>{node.label}</strong>
              <p>{node.message ?? node.status}</p>
            </div>
          </article>
        ))}
      </div>
      <h3>Event Stream</h3>
      <div className="event-stream">
        {events.map((event, index) => <p key={`${event}-${index}`}>{event}</p>)}
      </div>
    </aside>
  )
}
```

- [ ] **Step 4: Implement workspace page and app**

Create `frontend/src/features/workspace/WorkspacePage.tsx` with static state first:

```tsx
import { useMemo, useState } from 'react'
import { TaskControlPanel } from './TaskControlPanel'
import { ResultWorkspace } from './ResultWorkspace'
import { AgentTracePanel } from './AgentTracePanel'
import { INITIAL_TIMELINE } from '../tasks/timeline'
import type { TableSummary, TaskMode } from '../tasks/taskTypes'

const sampleTables: TableSummary[] = [
  { table_id: 'toy_source', tenant_id: 'default', table_name: 'Toy Source', row_count: 2, col_count: 1, status: 'READY' },
  { table_id: 'toy_target', tenant_id: 'default', table_name: 'Toy Target', row_count: 2, col_count: 1, status: 'READY' },
]

export function WorkspacePage() {
  const params = new URLSearchParams(window.location.search)
  const [mode, setMode] = useState<TaskMode>((params.get('mode') as TaskMode) || 'integrate')
  const [queryTableId, setQueryTableId] = useState(params.get('query_table_id') ?? '')
  const [sourceTableId, setSourceTableId] = useState(params.get('source_table_id') ?? '')
  const [targetTableId, setTargetTableId] = useState(params.get('target_table_id') ?? '')
  const tenantId = params.get('tenant_id') ?? import.meta.env.VITE_DEFAULT_TENANT_ID ?? 'default'
  const eventLines = useMemo(() => ['Workspace ready. Select tables and run AdaCascade.'], [])

  return (
    <main className="workbench-shell">
      <header className="top-bar">
        <div>
          <p className="eyebrow">Adaptive scenario matching · Cascaded filtering</p>
          <h1>AdaCascade Workbench</h1>
        </div>
        <div className="api-pill">API · Local Demo</div>
      </header>
      <div className="workbench-grid">
        <TaskControlPanel
          tenantId={tenantId}
          mode={mode}
          tables={sampleTables}
          queryTableId={queryTableId}
          sourceTableId={sourceTableId}
          targetTableId={targetTableId}
          isRunning={false}
          onModeChange={setMode}
          onQueryTableChange={setQueryTableId}
          onSourceTableChange={setSourceTableId}
          onTargetTableChange={setTargetTableId}
          onRun={() => undefined}
        />
        <ResultWorkspace task={null} />
        <AgentTracePanel timeline={INITIAL_TIMELINE} events={eventLines} />
      </div>
    </main>
  )
}
```

Modify `frontend/src/app/App.tsx`:

```tsx
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { WorkspacePage } from '../features/workspace/WorkspacePage'

const queryClient = new QueryClient()

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <WorkspacePage />
    </QueryClientProvider>
  )
}
```

- [ ] **Step 5: Apply polished workbench CSS**

Replace `frontend/src/styles/globals.css` with a full visual system:

```css
:root {
  --bg: #071019;
  --panel: rgba(10, 22, 34, 0.78);
  --panel-strong: rgba(13, 31, 48, 0.92);
  --line: rgba(141, 218, 255, 0.18);
  --text: #e6f7ff;
  --muted: #83a6b8;
  --cyan: #27d9ff;
  --green: #46f0a8;
  --violet: #a78bfa;
  --amber: #f8b84e;
  --red: #ff5d73;
  --shadow: 0 24px 80px rgba(0, 0, 0, 0.48);
  color: var(--text);
  background: var(--bg);
  font-family: "Aptos", "Segoe UI", sans-serif;
}

* { box-sizing: border-box; }

body {
  margin: 0;
  min-width: 1280px;
  min-height: 100vh;
  background:
    linear-gradient(rgba(39, 217, 255, 0.035) 1px, transparent 1px),
    linear-gradient(90deg, rgba(39, 217, 255, 0.035) 1px, transparent 1px),
    radial-gradient(circle at 18% 12%, rgba(39, 217, 255, 0.18), transparent 30rem),
    radial-gradient(circle at 78% 4%, rgba(167, 139, 250, 0.16), transparent 34rem),
    radial-gradient(circle at 50% 100%, rgba(70, 240, 168, 0.08), transparent 28rem),
    var(--bg);
  background-size: 48px 48px, 48px 48px, auto, auto, auto, auto;
}

button, input, select { font: inherit; }
button, select {
  border: 1px solid var(--line);
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.045);
  color: var(--text);
}
select { width: 100%; padding: 0.75rem 0.85rem; }
label { display: grid; gap: 0.45rem; color: var(--muted); font-size: 0.86rem; }

.workbench-shell { padding: 1.25rem; }
.top-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1rem 1.25rem 1.35rem;
}
.top-bar h1 {
  margin: 0;
  font-size: clamp(2rem, 4vw, 4rem);
  letter-spacing: -0.055em;
  line-height: 0.95;
}
.eyebrow {
  margin: 0 0 0.45rem;
  color: var(--cyan);
  font-size: 0.72rem;
  letter-spacing: 0.16em;
  text-transform: uppercase;
}
.api-pill, .status-badge {
  border: 1px solid var(--line);
  border-radius: 999px;
  padding: 0.45rem 0.8rem;
  background: rgba(39, 217, 255, 0.08);
  color: var(--cyan);
}
.workbench-grid {
  display: grid;
  grid-template-columns: 300px minmax(560px, 1fr) 360px;
  gap: 1rem;
  min-height: calc(100vh - 7.5rem);
}
.panel {
  border: 1px solid var(--line);
  border-radius: 28px;
  background: linear-gradient(145deg, var(--panel-strong), var(--panel));
  box-shadow: var(--shadow);
  backdrop-filter: blur(20px);
}
.control-panel, .trace-panel { padding: 1rem; }
.control-panel { display: flex; flex-direction: column; gap: 1rem; }
.control-panel h2, .trace-panel h2 { margin: 0; }
.run-button {
  margin-top: 0.5rem;
  padding: 0.9rem 1rem;
  border-color: rgba(39, 217, 255, 0.55);
  background: linear-gradient(135deg, rgba(39, 217, 255, 0.28), rgba(167, 139, 250, 0.22));
  color: white;
  cursor: pointer;
  box-shadow: 0 0 32px rgba(39, 217, 255, 0.14);
}
.run-button:disabled { opacity: 0.55; cursor: wait; }
.result-panel { padding: 1rem; overflow: hidden; }
.tab-strip { display: flex; gap: 0.5rem; margin-bottom: 1rem; }
.tab-strip button { padding: 0.55rem 0.85rem; }
.result-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; }
.result-row {
  display: grid;
  grid-template-columns: auto 1fr auto;
  gap: 0.75rem;
  align-items: center;
  margin-bottom: 0.65rem;
  padding: 0.75rem;
  border: 1px solid var(--line);
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.04);
}
.score-bar {
  position: relative;
  min-width: 86px;
  height: 28px;
  overflow: hidden;
  border: 1px solid var(--line);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.04);
}
.score-bar span {
  position: absolute;
  inset: 0 auto 0 0;
  background: linear-gradient(90deg, var(--cyan), var(--green));
  opacity: 0.6;
}
.score-bar strong {
  position: relative;
  display: block;
  padding: 0.35rem 0.55rem;
  text-align: right;
  font-size: 0.76rem;
}
.empty-state {
  display: grid;
  place-content: center;
  min-height: 100%;
  text-align: center;
  color: var(--muted);
}
.json-viewer {
  max-height: 240px;
  overflow: auto;
  padding: 1rem;
  border: 1px solid var(--line);
  border-radius: 18px;
  background: rgba(0, 0, 0, 0.24);
  color: #bfefff;
}
.timeline-list { display: grid; gap: 0.65rem; }
.timeline-node {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 0.75rem;
  padding: 0.7rem;
  border: 1px solid var(--line);
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.035);
}
.timeline-dot {
  width: 0.78rem;
  height: 0.78rem;
  margin-top: 0.25rem;
  border-radius: 999px;
  background: var(--muted);
}
.timeline-running .timeline-dot { background: var(--cyan); box-shadow: 0 0 18px var(--cyan); }
.timeline-success .timeline-dot { background: var(--green); box-shadow: 0 0 18px var(--green); }
.timeline-degraded .timeline-dot { background: var(--amber); box-shadow: 0 0 18px var(--amber); }
.timeline-failed .timeline-dot { background: var(--red); box-shadow: 0 0 18px var(--red); }
.timeline-node strong { display: block; }
.timeline-node p { margin: 0.15rem 0 0; color: var(--muted); font-size: 0.82rem; }
.event-stream {
  max-height: 220px;
  overflow: auto;
  color: var(--muted);
  font-family: "Cascadia Code", monospace;
  font-size: 0.78rem;
}
```

- [ ] **Step 6: Run workspace component tests**

Run:

```bash
cd frontend && npm run test -- TaskControlPanel.test.tsx
```

Expected: PASS.

- [ ] **Step 7: Start frontend and visually inspect**

Run:

```bash
cd frontend && npm run dev
```

Open `http://localhost:5173/workspace?tenant_id=default&mode=integrate&query_table_id=toy_source`.

Expected: dark three-column workbench, URL params reflected in controls, no console errors.

- [ ] **Step 8: Commit UI shell**

```bash
git add frontend/src frontend/index.html
git commit -m "feat(m3.5): build polished workbench shell"
```

---

## Task 8: Wire frontend to backend REST and SSE

**Files:**
- Modify: `frontend/src/features/workspace/WorkspacePage.tsx`
- Create: `frontend/src/features/tasks/taskStore.ts`
- Test: `frontend/src/features/tasks/taskStore.test.ts`

- [ ] **Step 1: Write task store test**

Create `frontend/src/features/tasks/taskStore.test.ts`:

```ts
import { describe, expect, it } from 'vitest'
import { useTaskStore } from './taskStore'

const startedEvent = {
  task_id: 'task-1',
  type: 'agent_started' as const,
  agent: 'Retrieval' as const,
  layer: 'L1',
  timestamp: '2026-04-27T00:00:00Z',
}

describe('taskStore', () => {
  it('tracks the current task and live timeline events', () => {
    useTaskStore.getState().resetLiveState()
    useTaskStore.getState().setCurrentTaskId('task-1')
    useTaskStore.getState().appendEvent(startedEvent)

    const state = useTaskStore.getState()
    expect(state.currentTaskId).toBe('task-1')
    expect(state.events).toHaveLength(1)
    expect(state.timeline['Retrieval:L1'].status).toBe('running')
  })
})
```

Expected: this test is written before `taskStore.ts`, so it initially fails because the module does not exist.

- [ ] **Step 2: Create task store**

Create `frontend/src/features/tasks/taskStore.ts`:

```ts
import { create } from 'zustand'
import { applyTaskEvent, INITIAL_TIMELINE, type TimelineState } from './timeline'
import type { TaskEvent } from './taskTypes'

type TaskStore = {
  currentTaskId: string | null
  events: TaskEvent[]
  timeline: TimelineState
  setCurrentTaskId: (taskId: string) => void
  appendEvent: (event: TaskEvent) => void
  resetLiveState: () => void
}

export const useTaskStore = create<TaskStore>((set) => ({
  currentTaskId: null,
  events: [],
  timeline: INITIAL_TIMELINE,
  setCurrentTaskId: (taskId) => set({ currentTaskId: taskId }),
  appendEvent: (event) => set((state) => ({
    events: [...state.events, event],
    timeline: applyTaskEvent(state.timeline, event),
  })),
  resetLiveState: () => set({ events: [], timeline: INITIAL_TIMELINE }),
}))
```

- [ ] **Step 3: Run task store test**

Run:

```bash
cd frontend && npm run test -- taskStore.test.ts
```

Expected: PASS.

- [ ] **Step 4: Wire workspace data fetching and run action**

Replace `frontend/src/features/workspace/WorkspacePage.tsx` with:

```tsx
import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { listTables } from '../../api/tables'
import { getTask, startDiscover, startIntegrate, startMatch } from '../../api/tasks'
import { subscribeTaskEvents } from '../../api/events'
import { AgentTracePanel } from './AgentTracePanel'
import { ResultWorkspace } from './ResultWorkspace'
import { TaskControlPanel } from './TaskControlPanel'
import { useTaskStore } from '../tasks/taskStore'
import type { TaskMode } from '../tasks/taskTypes'

export function WorkspacePage() {
  const params = new URLSearchParams(window.location.search)
  const [mode, setMode] = useState<TaskMode>((params.get('mode') as TaskMode) || 'integrate')
  const [queryTableId, setQueryTableId] = useState(params.get('query_table_id') ?? '')
  const [sourceTableId, setSourceTableId] = useState(params.get('source_table_id') ?? '')
  const [targetTableId, setTargetTableId] = useState(params.get('target_table_id') ?? '')
  const tenantId = params.get('tenant_id') ?? import.meta.env.VITE_DEFAULT_TENANT_ID ?? 'default'
  const queryClient = useQueryClient()
  const { currentTaskId, setCurrentTaskId, appendEvent, resetLiveState, events, timeline } = useTaskStore()

  const tablesQuery = useQuery({ queryKey: ['tables', tenantId], queryFn: () => listTables(tenantId) })
  const taskQuery = useQuery({
    queryKey: ['task', tenantId, currentTaskId],
    queryFn: () => getTask(tenantId, currentTaskId as string),
    enabled: Boolean(currentTaskId),
  })

  const startTask = useMutation({
    mutationFn: async () => {
      if (mode === 'discover') return startDiscover(tenantId, queryTableId)
      if (mode === 'integrate') return startIntegrate(tenantId, queryTableId)
      return startMatch(tenantId, sourceTableId, targetTableId)
    },
    onSuccess: (response) => {
      resetLiveState()
      setCurrentTaskId(response.task_id)
    },
  })

  useEffect(() => {
    if (!currentTaskId) return undefined
    const controller = new AbortController()
    void subscribeTaskEvents(tenantId, currentTaskId, (event) => {
      appendEvent(event)
      if (event.type === 'task_completed') {
        void queryClient.invalidateQueries({ queryKey: ['task', tenantId, currentTaskId] })
        controller.abort()
      }
    }, controller.signal)
    return () => controller.abort()
  }, [appendEvent, currentTaskId, queryClient, tenantId])

  const eventLines = events.map((event) => event.message ?? `${event.type} ${event.agent ?? ''} ${event.layer ?? ''}`)

  return (
    <main className="workbench-shell">
      <header className="top-bar">
        <div>
          <p className="eyebrow">Adaptive scenario matching · Cascaded filtering</p>
          <h1>AdaCascade Workbench</h1>
        </div>
        <div className="api-pill">Tenant · {tenantId}</div>
      </header>
      <div className="workbench-grid">
        <TaskControlPanel
          tenantId={tenantId}
          mode={mode}
          tables={tablesQuery.data?.items ?? []}
          queryTableId={queryTableId}
          sourceTableId={sourceTableId}
          targetTableId={targetTableId}
          isRunning={startTask.isPending || taskQuery.data?.status === 'RUNNING'}
          onModeChange={setMode}
          onQueryTableChange={setQueryTableId}
          onSourceTableChange={setSourceTableId}
          onTargetTableChange={setTargetTableId}
          onRun={() => startTask.mutate()}
        />
        <ResultWorkspace task={taskQuery.data ?? null} />
        <AgentTracePanel timeline={timeline} events={eventLines} />
      </div>
    </main>
  )
}
```

- [ ] **Step 5: Run frontend build**

Run:

```bash
cd frontend && npm run build
```

Expected: PASS.

- [ ] **Step 6: Run backend and frontend smoke manually**

Start backend separately according to project instructions:

```bash
NO_PROXY=localhost,127.0.0.1 bash scripts/start_api.sh
```

Start frontend:

```bash
cd frontend && npm run dev
```

Open `http://localhost:5173/workspace` and run discover against a READY table.

Expected: task starts, trace receives SSE events, final result loads.

- [ ] **Step 7: Commit REST/SSE wiring**

```bash
git add frontend/src/features/workspace/WorkspacePage.tsx frontend/src/features/tasks/taskStore.ts frontend/src/features/tasks/taskStore.test.ts
git commit -m "feat(m3.5): wire workbench to backend tasks"
```

---

## Task 9: React Flow result graph

**Files:**
- Create: `frontend/src/features/graph/ResultGraph.tsx`
- Modify: `frontend/src/features/workspace/ResultWorkspace.tsx`
- Test: `frontend/src/features/graph/graphModel.test.ts`

- [ ] **Step 1: Implement ResultGraph**

Create `frontend/src/features/graph/ResultGraph.tsx`:

```tsx
import ReactFlow, { Background, Controls, MarkerType, type Edge, type Node } from 'reactflow'
import 'reactflow/dist/style.css'
import type { TaskGraph } from './graphTypes'

function nodeColor(kind: string) {
  if (kind.includes('query') || kind.includes('source')) return '#27d9ff'
  if (kind.includes('candidate') || kind.includes('target')) return '#46f0a8'
  return '#a78bfa'
}

export function ResultGraph({ graph }: { graph: TaskGraph }) {
  const nodes: Node[] = graph.nodes.map((node, index) => ({
    id: node.id,
    position: { x: (index % 3) * 260, y: Math.floor(index / 3) * 130 },
    data: { label: node.label },
    style: {
      border: `1px solid ${nodeColor(node.kind)}`,
      background: 'rgba(8, 16, 24, 0.92)',
      color: '#e6f7ff',
      borderRadius: 18,
      boxShadow: `0 0 22px ${nodeColor(node.kind)}33`,
    },
  }))

  const edges: Edge[] = graph.edges.map((edge) => ({
    id: edge.id,
    source: edge.source,
    target: edge.target,
    label: edge.label,
    markerEnd: { type: MarkerType.ArrowClosed },
    style: { stroke: edge.kind === 'mapping' ? '#a78bfa' : '#27d9ff', strokeWidth: 2 },
    labelStyle: { fill: '#e6f7ff' },
  }))

  return (
    <div className="graph-canvas">
      <ReactFlow nodes={nodes} edges={edges} fitView>
        <Background color="rgba(141, 218, 255, 0.18)" gap={24} />
        <Controls />
      </ReactFlow>
    </div>
  )
}
```

- [ ] **Step 2: Render graph in ResultWorkspace**

Modify `frontend/src/features/workspace/ResultWorkspace.tsx` imports:

```tsx
import { ResultGraph } from '../graph/ResultGraph'
import { buildTaskGraph } from '../graph/graphModel'
```

Inside `ResultWorkspace`, compute and render graph before `result-grid`:

```tsx
  const graph = buildTaskGraph(task)
```

Then add:

```tsx
      <ResultGraph graph={graph} />
```

- [ ] **Step 3: Add graph CSS**

Append to `frontend/src/styles/globals.css`:

```css
.graph-canvas {
  height: 430px;
  margin-bottom: 1rem;
  overflow: hidden;
  border: 1px solid var(--line);
  border-radius: 22px;
  background: rgba(0, 0, 0, 0.22);
}
.react-flow__controls button {
  background: rgba(8, 16, 24, 0.92);
  color: var(--text);
  border-color: var(--line);
}
.react-flow__edge-path {
  filter: drop-shadow(0 0 8px rgba(39, 217, 255, 0.45));
}
```

- [ ] **Step 4: Run frontend build**

Run:

```bash
cd frontend && npm run build
```

Expected: PASS.

- [ ] **Step 5: Visually inspect graph**

Run:

```bash
cd frontend && npm run dev
```

Open a completed task in the UI or use local mock data during development.

Expected: graph renders table and column nodes with glowing dark workbench styling.

- [ ] **Step 6: Commit graph UI**

```bash
git add frontend/src/features/graph/ResultGraph.tsx frontend/src/features/workspace/ResultWorkspace.tsx frontend/src/styles/globals.css
git commit -m "feat(m3.5): render task result graph"
```

---

## Task 10: Playwright demo flow and final verification

**Files:**
- Create: `frontend/e2e/workspace.spec.ts`
- Modify: `TODO.md`

- [ ] **Step 1: Write Playwright route-prefill smoke test**

Create `frontend/e2e/workspace.spec.ts`:

```ts
import { expect, test } from '@playwright/test'

test('workspace loads external jump context without auto-running a task', async ({ page }) => {
  await page.route('**/tables?**', async (route) => {
    await route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify({
        items: [
          { table_id: 'toy_source', tenant_id: 'default', table_name: 'Toy Source', row_count: 2, col_count: 1, status: 'READY' },
        ],
        total: 1,
        limit: 200,
        offset: 0,
      }),
    })
  })
  await page.goto('/workspace?tenant_id=default&mode=integrate&query_table_id=toy_source')
  await expect(page.getByRole('heading', { name: 'AdaCascade Workbench' })).toBeVisible()
  await expect(page.getByLabel('Mode')).toHaveValue('integrate')
  await expect(page.getByLabel('Query table')).toHaveValue('toy_source')
  await expect(page.getByRole('button', { name: 'Run AdaCascade' })).toBeEnabled()
})
```

- [ ] **Step 2: Run Playwright test**

Run:

```bash
cd frontend && npm run test:e2e
```

Expected: PASS. If browsers are missing, run:

```bash
cd frontend && npx playwright install chromium
npm run test:e2e
```

- [ ] **Step 3: Run full frontend verification**

Run:

```bash
cd frontend && npm run lint && npm run test && npm run build
```

Expected: PASS.

- [ ] **Step 4: Run backend verification**

Run:

```bash
ruff format adacascade/ tests/
ruff check adacascade/ tests/ scripts/
pytest tests/unit/ -v
pytest tests/integration/ -v
mypy --strict adacascade/
```

Expected: PASS.

- [ ] **Step 5: Update TODO M3.5 completion state**

Modify `TODO.md` M3.5 section:

```markdown
- [x] 创建 `frontend/`：React + Vite + TypeScript 独立前端
- [x] 实现 `/workspace` 三栏工作台：任务控制区、结果图区、Agent Trace 区
- [x] 接入现有后端 REST：`GET /tables`、`POST /discover`、`POST /match`、`POST /integrate`、`GET /tasks/{task_id}`
- [x] 新增后端 SSE：`GET /tasks/{task_id}/events` 与进程内任务事件总线
- [x] 增加 Agent/Layer 事件 emit 点：Planner、Profiling、Retrieval L1/L2/L3、Matcher filtering/LLM/decision
- [x] 实现 React Flow 图谱：ranking → discovery graph，mappings → column mapping graph
- [x] 实现 Vitest 单元/组件测试与 Playwright 演示 E2E
- [x] 明确本地 demo 安全边界：`VITE_API_KEY` 仅限本地可信环境，不可公网部署
```

Only mark an item complete after its tests pass.

- [ ] **Step 6: Commit final M3.5 verification**

```bash
git add TODO.md frontend/e2e/workspace.spec.ts
git commit -m "test(m3.5): add frontend demo acceptance coverage"
```

---

## Self-Review Checklist

- Spec coverage:
  - Frontend is separate under `frontend/`: Task 3.
  - `/workspace` three-column workbench: Task 7.
  - REST task creation and result fetching: Tasks 4 and 8.
  - SSE endpoint and event bus: Tasks 1 and 2.
  - Agent/layer trace: Tasks 2, 6, 7, 8.
  - Graph conversion and React Flow visualization: Tasks 5 and 9.
  - Local-only API key warning: Task 3 env file and existing design doc.
  - Vitest and Playwright: Tasks 3, 5, 6, 7, 10.
- Placeholder scan: no `TBD`, `TODO`, or unspecified implementation placeholders are used as work instructions.
- Type consistency:
  - `TaskEvent`, `TaskDetail`, `GraphNode`, `GraphEdge`, and `TimelineState` are defined before use.
  - API client return types match existing backend response shapes from `/tasks/{task_id}`.
  - Graph mapping follows `docs/frontend_demo_design.md` field mapping.

---

## Execution Handoff

Plan complete and saved to `docs/frontend_demo_implementation_plan.md`.

Two execution options:

1. **Subagent-Driven (recommended)** - dispatch a fresh subagent per task, review between tasks, fast iteration.

2. **Inline Execution** - execute tasks in this session using executing-plans, batch execution with checkpoints.
