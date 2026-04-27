# AdaCascade Frontend Demo Design

## 1. Background and Goal

AdaCascade already provides local FastAPI endpoints for table discovery, schema matching, and integrated discovery-plus-matching tasks. The next step is a directly demonstrable frontend that can be opened from the research-group system through a simple button jump, while still working as a standalone local operation console.

The frontend should support three modes:

- Data discovery: find candidate tables for a query table.
- Schema matching: align columns between a source table and a target table.
- Integrated flow: run discovery and matching in one task.

The demo must make the multi-agent process visible. Users should see each agent and important internal layer progress in real time, then inspect graph-like results and detailed tables after completion.

## 2. Scope

### In scope for the first version

- A separate React + Vite + TypeScript frontend under `frontend/`.
- A `/workspace` page using a three-column workbench layout.
- URL-parameter based context import from the research-group system.
- Existing table selection through the current backend table list API.
- Task creation for `/discover`, `/match`, and `/integrate`.
- SSE-based real-time stage progress.
- Agent + layer timeline visualization.
- Result graph, ranking table, mapping table, and raw JSON views.
- Local demo authentication using the existing API key and tenant headers.

### Out of scope for the first version

- Login, user management, or multi-user permission UI.
- Uploading new tables from the frontend.
- Replacing FastAPI background tasks with Celery, Redis, or another queue.
- Splitting AdaCascade into microservices.
- Full historical task search backed by a new database query API.
- Embedding the frontend inside the research-group system.
- Automatically running tasks immediately after external-system jump.
- Showing complete prompts or raw LLM responses by default.

## 3. Product Positioning

The frontend is a hybrid of a presentation demo and a real operation console:

- It should be visually strong enough for paper defense, lab presentation, and project demonstration.
- It should still execute real backend tasks and show real task data, not hard-coded mock results.
- It should be easy for the research-group system to link into without deep integration.

The preferred visual style is a dark research workbench: professional, dense enough for technical details, but with clear graph and timeline highlights.

## 4. Overall Architecture

```text
Research-group system
    │
    │ button jump with URL parameters
    ▼
React/Vite frontend: /workspace
    │
    │ REST + SSE, Authorization + X-Tenant-Id
    ▼
Existing FastAPI AdaCascade service
    ├── /tables
    ├── /discover
    ├── /match
    ├── /integrate
    ├── /tasks/{task_id}
    └── /tasks/{task_id}/events  (new)
```

The frontend and backend remain separated:

- The frontend owns presentation, browser state, graph rendering, task selection, and result drill-downs.
- The backend owns task execution, persistence, tenant scoping, metrics, and event generation.
- The research-group system only needs to provide a button or link.

The existing FastAPI service remains a single-process monolith as required by the system design. No microservice split is introduced.

## 5. External Jump Contract

The research-group system links to the frontend with URL parameters:

```text
/workspace?tenant_id=default&mode=integrate&query_table_id=abc
/workspace?tenant_id=default&mode=discover&query_table_id=abc
/workspace?tenant_id=default&mode=match&source_table_id=abc&target_table_id=def
```

Supported parameters:

| Parameter | Required | Meaning |
|---|---:|---|
| `tenant_id` | No | Tenant context. Defaults to `default` if omitted. |
| `mode` | No | `discover`, `match`, or `integrate`. |
| `query_table_id` | For discover/integrate | Query table for discovery or integrated flow. |
| `source_table_id` | For match | Source table for direct schema matching. |
| `target_table_id` | For match | Target table for direct schema matching. |

The frontend should prefill controls from these parameters, but should not automatically execute the task. It should show a confirmation state such as: “Context imported from external system. Confirm and run.” This avoids accidental GPU or LLM consumption from a mistaken click.

## 6. Workspace Layout

The first version has one main page: `/workspace`.

```text
┌──────────────────────────────────────────────────────────────┐
│ Top Bar: AdaCascade / tenant / API status / mode / run button │
├───────────────┬──────────────────────────────┬───────────────┤
│ Left Control   │ Center Result Workspace       │ Right Trace    │
│ Panel          │                              │ Panel          │
│               │                              │               │
│ - mode select  │ - graph view                  │ - SSE events   │
│ - table select │ - ranking table               │ - timeline     │
│ - run task     │ - mapping table               │ - input/output │
│ - session tasks│ - raw JSON                    │ - degradation  │
└───────────────┴──────────────────────────────┴───────────────┘
```

### 6.1 Top bar

The top bar shows:

- Product name: AdaCascade.
- Current tenant.
- Backend connectivity indicator.
- Current task mode.
- Main run button.

### 6.2 Left control panel

The left panel is used to select and run tasks.

Controls:

- Tenant display from URL or default config.
- Mode selector:
  - Data discovery.
  - Schema matching.
  - Integrated flow.
- Existing table selector from `GET /tables`.
- Query table selector for discovery/integrate.
- Source and target table selectors for match.
- Run button.
- Browser-session task list.

The first version does not need a persistent task history API. It can keep tasks created during the current browser session. A later version can add `GET /tasks` for durable task history.

### 6.3 Center result workspace

The center panel has tabs:

1. `Graph`
2. `Ranking`
3. `Mappings`
4. `Raw JSON`

The Graph tab is the default. Ranking and Mappings tables are linked with the graph. Raw JSON shows the original `/tasks/{task_id}` response to prove that the UI is backed by real backend data.

### 6.4 Right trace panel

The right panel is the main process explanation area. It shows:

- Agent/layer timeline.
- Real-time event stream.
- Input/output summary for the selected agent or layer.
- Latency, input size, output size, token count, and degradation status when available.

## 7. Task Flow

### 7.1 Discovery mode

1. User selects `discover`.
2. User selects a query table.
3. Frontend calls `POST /discover`.
4. Frontend receives `task_id`.
5. Frontend subscribes to `GET /tasks/{task_id}/events`.
6. Timeline updates as Planner, Profiling, Retrieval L1/L2/L3 run.
7. On `task_completed`, frontend fetches `GET /tasks/{task_id}`.
8. Center panel shows ranking graph and ranking table.

### 7.2 Match mode

1. User selects `match`.
2. User selects source and target tables.
3. Frontend calls `POST /match`.
4. Frontend receives `task_id`.
5. Frontend subscribes to task events.
6. Timeline updates through Planner, Profiling if needed, and Matcher layers.
7. On completion, frontend fetches task result.
8. Center panel shows column mapping graph and mapping table.

### 7.3 Integrated mode

1. User selects `integrate`.
2. User selects a query table.
3. Frontend calls `POST /integrate`.
4. Frontend subscribes to task events.
5. Timeline shows Planner, Profiling, Retrieval L1/L2/L3, and Matcher.
6. On completion, frontend fetches final task result.
7. Center panel shows discovery results and matching results.

For integrated mode, the graph should default to the top-ranked candidate table. If the backend result does not yet associate mappings with each candidate table, the UI shows global mappings first and can later be refined when the backend stores candidate-specific mapping groups.

## 8. SSE Event API

### 8.1 Endpoint

```text
GET /tasks/{task_id}/events
```

Headers:

```text
Authorization: Bearer <API_KEY>
X-Tenant-Id: <tenant_id>
```

Response:

```text
Content-Type: text/event-stream
```

The frontend should use `@microsoft/fetch-event-source` instead of the browser-native `EventSource`, because it supports custom headers. This keeps the existing bearer-token and tenant-header model intact.

### 8.2 Event types

The first version emits stage-level events:

| Event | Meaning |
|---|---|
| `task_created` | Task row was created. |
| `agent_started` | Agent or layer started. |
| `agent_completed` | Agent or layer completed successfully. |
| `agent_degraded` | Agent or layer completed with fallback/degradation. |
| `agent_failed` | Agent or layer failed. |
| `task_completed` | Task finished successfully or failed. |
| `heartbeat` | Keep-alive event. |

### 8.3 Event shape

```ts
type TaskEvent = {
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

### 8.4 Example SSE stream

```text
event: agent_started
data: {"task_id":"...","type":"agent_started","agent":"Retrieval","layer":"L1","message":"Retrieval L1 started","timestamp":"..."}

event: agent_completed
data: {"task_id":"...","type":"agent_completed","agent":"Retrieval","layer":"L1","input_size":1534,"output_size":80,"latency_ms":120,"timestamp":"..."}

event: task_completed
data: {"task_id":"...","type":"task_completed","status":"SUCCESS","timestamp":"..."}
```

### 8.5 Backend event strategy

The first version uses an in-process event bus:

- Key: `task_id`.
- Value: async queue or listener set.
- Agent wrapper code emits events during execution.
- The SSE endpoint subscribes to the queue for one task.
- Task completion sends `task_completed` and closes the stream.
- Heartbeats are sent every 5-10 seconds while the task is running.

SSE is not the source of truth. It is only the live progress channel. The durable source of truth remains `IntegrationTask`, `AgentStep`, `DiscoveryResult`, and `ColumnMapping` in the database.

If the page refreshes after completion, the frontend rebuilds the final timeline from `GET /tasks/{task_id}` and its `trace` field. If the backend restarts during a running task, the frontend should show that the live connection was interrupted and allow the user to refresh the task status.

## 9. Agent Timeline Model

The right trace panel should represent these nodes:

```text
Planner
Profiling
Retrieval
  ├── L1: TF-IDF + type Jaccard
  ├── L2: Qdrant vector recall
  └── L3: LLM verification
Matcher
  ├── candidate filtering
  ├── LLM verification
  └── decision
```

Each node status:

- `pending`
- `running`
- `success`
- `degraded`
- `failed`

Each node detail panel may show:

- Input size.
- Output size.
- Latency.
- LLM tokens.
- Recall loss.
- Reason for degradation.
- Fallback strategy.

## 10. Graph Visualization

The center graph is a visualization projection of task results. It is not a graph database.

### 10.1 Graph node model

```ts
type GraphNode = {
  id: string
  kind:
    | 'query_table'
    | 'candidate_table'
    | 'source_table'
    | 'target_table'
    | 'source_column'
    | 'target_column'
  label: string
  table_id?: string
  column_id?: string
  status?: 'normal' | 'matched' | 'degraded' | 'failed'
  metrics?: Record<string, number | string>
}
```

### 10.2 Graph edge model

```ts
type GraphEdge = {
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
```

### 10.3 Discovery graph

Discovery mode shows table-level relationships:

```text
query table
  ├── rank #1 candidate table
  ├── rank #2 candidate table
  └── rank #3 candidate table
```

Discovery edges use ranking score as weight. Edge metrics include L1/L2/L3 layer scores when available.

### 10.4 Match graph

Match mode shows column-level relationships:

```text
source columns        target columns
name        ───────▶  person_name
age         ───────▶  age_years
hospital_id ───────▶  provider_id
```

Mapping edges use confidence as weight. Edge details show scenario and reasoning.

### 10.5 Integrated graph

Integrated mode combines the two levels:

- Upper section: query table to candidate tables.
- Lower section: query/source columns to selected target/candidate columns.

The UI defaults to the top-ranked candidate table. Clicking a candidate table changes the focused mapping section when candidate-specific mappings are available.

### 10.6 Interaction rules

- Clicking a Ranking row highlights the candidate node and discovery edge.
- Clicking a Mapping row highlights the source column, target column, and mapping edge.
- Clicking a graph node or edge opens a details drawer.
- Details drawer allows copying `task_id`, `table_id`, or `column_id`.

### 10.7 Recommended graph library

Use React Flow for the first version. It is well suited for directed graph rendering, custom nodes, clickable edges, and controlled layouts. Add `dagre` only if automatic layered layout is needed.

## 11. Frontend Technical Design

### 11.1 Directory structure

```text
frontend/
├── package.json
├── vite.config.ts
├── index.html
└── src/
    ├── main.tsx
    ├── app/
    │   ├── App.tsx
    │   └── router.tsx
    ├── api/
    │   ├── client.ts
    │   ├── tables.ts
    │   ├── tasks.ts
    │   └── events.ts
    ├── features/
    │   ├── workspace/
    │   │   ├── WorkspacePage.tsx
    │   │   ├── TaskControlPanel.tsx
    │   │   ├── ResultWorkspace.tsx
    │   │   └── AgentTracePanel.tsx
    │   ├── graph/
    │   │   ├── ResultGraph.tsx
    │   │   ├── graphModel.ts
    │   │   └── graphLayout.ts
    │   └── tasks/
    │       ├── taskTypes.ts
    │       └── taskStore.ts
    ├── components/
    │   ├── StatusBadge.tsx
    │   ├── ScoreBar.tsx
    │   ├── EmptyState.tsx
    │   └── JsonViewer.tsx
    └── styles/
        └── globals.css
```

### 11.2 Module boundaries

`api/`:

- Owns HTTP and SSE calls.
- Adds `Authorization` and `X-Tenant-Id` headers.
- Reads `VITE_API_BASE_URL` and `VITE_API_KEY` from environment.
- Does not own UI state.

`features/workspace/`:

- Owns the workbench page.
- Coordinates selected mode, selected tables, current task, and selected graph item.

`features/graph/`:

- Converts task results into graph nodes and edges.
- Renders React Flow.
- Does not call backend APIs directly.

`features/tasks/`:

- Defines task and event types.
- Maintains current browser-session task list.
- Maintains SSE event buffers by task id.

`components/`:

- Reusable UI building blocks with no backend knowledge.

### 11.3 State management

Use two layers:

- React Query for server data:
  - `/tables`
  - `/tasks/{task_id}`
- Zustand for UI and live event state:
  - selected mode
  - selected tables
  - current task id
  - session task list
  - selected graph item
  - SSE event buffer

Avoid Redux in the first version. It is unnecessary for this scope.

### 11.4 Environment variables

Frontend environment variables:

```text
VITE_API_BASE_URL=http://localhost:8080
VITE_API_KEY=dev-local-token
VITE_DEFAULT_TENANT_ID=default
```

The first version is a local demo tool. Later, production deployment should not expose privileged long-lived API keys in browser code. The external-system integration can move to a short-lived session token flow when needed.

## 12. Backend Minimum Additions

To support the frontend, add only the minimum backend changes:

1. `GET /tasks/{task_id}/events`
   - SSE endpoint scoped by bearer token and tenant header.

2. In-process task event bus
   - Subscribe by `task_id`.
   - Emit live task events.
   - Remove listeners after completion.

3. Agent/layer event emit points
   - Planner start/complete.
   - Profiling start/complete.
   - Retrieval L1/L2/L3 start/complete/degraded.
   - Matcher candidate filtering / LLM verification / decision start/complete/degraded.

4. Optional future endpoint: `GET /tasks`
   - Durable history list.
   - Not required for first version.

5. Optional future endpoint: `GET /tasks/{task_id}/graph`
   - Backend-normalized graph data.
   - Not required for first version because the frontend can derive graph data from task results.

## 13. Error and Degradation UX

The UI should distinguish these states:

- Backend unavailable.
- Unauthorized or wrong API key.
- Tenant has no tables.
- Task creation failed.
- SSE connection interrupted.
- Task failed.
- Task succeeded with degradation.

Degraded state should be shown as orange, not red. It means the system returned a controlled fallback result. Failed state should be red and should show the backend error message when available.

If SSE disconnects, the frontend must not mark the task failed. It should show a connection warning and offer “Refresh task status,” which calls `GET /tasks/{task_id}`.

## 14. Testing Strategy

### 14.1 Frontend unit tests

Test pure conversion logic:

- Task result to graph nodes/edges.
- SSE events to timeline state.
- URL parameters to initial workspace state.

### 14.2 Component tests

Test key components with mock data:

- `TaskControlPanel` renders modes and table selectors.
- `AgentTracePanel` renders running, success, degraded, and failed nodes.
- `ResultWorkspace` switches between Graph, Ranking, Mappings, and Raw JSON.

### 14.3 End-to-end tests

Use Playwright for the demo flow:

- Open `/workspace`.
- Select discover, match, and integrate modes.
- Start a task against mocked or local backend data.
- Verify timeline updates.
- Verify final graph, ranking, and mappings render.
- Verify URL parameters prefill the workspace.

## 15. Implementation Milestones

1. Frontend scaffold and API client.
2. Workspace layout and table selection.
3. Task creation for three modes.
4. Backend SSE event bus and `/tasks/{task_id}/events`.
5. Agent/layer event emission.
6. Agent trace panel with live events.
7. Task result fetch and tabs.
8. React Flow graph conversion and rendering.
9. Playwright demo test.
10. Polish for presentation.

## 16. Open Future Extensions

These are intentionally not part of the first version:

- Frontend upload and profiling progress.
- Durable task history browser.
- Short-lived external-system session tokens.
- Candidate-specific mapping groups for integrated mode.
- Full prompt and raw LLM response debug mode.
- User-level access control.
- Production build packaging and reverse-proxy deployment.
