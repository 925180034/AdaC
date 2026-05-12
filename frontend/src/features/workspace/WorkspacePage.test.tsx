import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import userEvent from '@testing-library/user-event'
import { render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { LlmRuntimeInfo } from '../../api/runtime'
import { getLlmRuntime, updateLlmRuntime } from '../../api/runtime'
import type { ListTablesResponse } from '../../api/tables'
import { listTables } from '../../api/tables'
import { cancelTask, getTask, startDiscover, startIntegrate } from '../../api/tasks'
import { useTaskStore } from '../tasks/taskStore'
import type { TaskDetail } from '../tasks/taskTypes'
import { WorkspacePage } from './WorkspacePage'

vi.mock('../../api/runtime', () => ({
  getLlmRuntime: vi.fn(),
  updateLlmRuntime: vi.fn(),
}))

vi.mock('../../api/tables', () => ({
  listTables: vi.fn(),
}))

vi.mock('../../api/events', () => ({
  subscribeTaskEvents: vi.fn(() => Promise.resolve()),
}))

vi.mock('../../api/tasks', () => ({
  cancelTask: vi.fn(),
  getTask: vi.fn(),
  startDiscover: vi.fn(),
  startIntegrate: vi.fn(),
  startMatch: vi.fn(),
}))

const tablesResponse: ListTablesResponse = {
  total: 1,
  offset: 0,
  limit: 200,
  items: [
    {
      table_id: 'default_table',
      tenant_id: 'default',
      table_name: 'Default Tenant Table',
      row_count: 10,
      col_count: 3,
      status: 'READY',
    },
  ],
}

const benchmarkTablesResponse: ListTablesResponse = {
  total: 1,
  offset: 0,
  limit: 200,
  items: [
    {
      table_id: 'benchmark_table',
      tenant_id: 'benchmark',
      table_name: 'Benchmark Tenant Table',
      row_count: 1000,
      col_count: 12,
      status: 'READY',
    },
  ],
}

const localRuntime: LlmRuntimeInfo = {
  backend: 'local',
  base_url: 'http://localhost:8000/v1',
  model: 'qwen3.5:9b',
  api_key_configured: false,
}

const apiRuntime: LlmRuntimeInfo = {
  backend: 'api',
  base_url: 'https://api.deepseek.com/v1',
  model: 'deepseek-chat',
  api_key_configured: true,
}

const runningTask: TaskDetail = {
  task_id: 'task-running',
  tenant_id: 'default',
  task_type: 'INTEGRATE',
  query_table_id: 'default_table',
  target_table_id: null,
  status: 'RUNNING',
  submitted_at: '2026-04-28T00:00:00Z',
  finished_at: null,
  error_message: null,
  plan_config: null,
  trace: [],
  ranking: [],
  mappings: [],
}

function renderWorkspace() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })

  const result = render(
    <QueryClientProvider client={queryClient}>
      <WorkspacePage />
    </QueryClientProvider>,
  )

  return { queryClient, ...result }
}

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason?: unknown) => void
  const promise = new Promise<T>((promiseResolve, promiseReject) => {
    resolve = promiseResolve
    reject = promiseReject
  })

  return { promise, resolve, reject }
}

describe('WorkspacePage', () => {
  beforeEach(() => {
    window.history.replaceState(null, '', '/')
    window.localStorage.clear()
    document.documentElement.removeAttribute('data-theme')
    vi.clearAllMocks()
    useTaskStore.setState({ currentTaskId: null, events: [] })
    vi.mocked(listTables).mockImplementation((tenantId) =>
      Promise.resolve(tenantId === 'benchmark' ? benchmarkTablesResponse : tablesResponse),
    )
    vi.mocked(getLlmRuntime).mockResolvedValue(localRuntime)
    vi.mocked(updateLlmRuntime).mockResolvedValue(apiRuntime)
    vi.mocked(getTask).mockResolvedValue(runningTask)
    vi.mocked(cancelTask).mockResolvedValue({ ...runningTask, status: 'FAILED', error_message: 'Task cancelled by user' })
    vi.mocked(startIntegrate).mockResolvedValue({ task_id: 'task-running', status: 'RUNNING', state: {} })
    vi.mocked(startDiscover).mockResolvedValue({ task_id: 'task-running', status: 'RUNNING', state: {} })
  })

  it('loads tables for the default tenant when no tenant is in the URL', async () => {
    renderWorkspace()

    await waitFor(() => expect(listTables).toHaveBeenCalledWith('default'))
    expect(await screen.findByText('Default Tenant Table · 10 × 3')).toBeInTheDocument()
  })

  it('uses the stored Chinese language preference for primary workspace copy', async () => {
    window.localStorage.setItem('adacascade.language', 'zh')
    renderWorkspace()

    expect(await screen.findByRole('heading', { name: 'AdaCascade 工作台' })).toBeInTheDocument()
    expect(screen.getByLabelText('本地演示安全提醒')).toHaveTextContent('本地演示环境')
  })

  it('keeps runtime controls disabled and unselected while runtime info is loading', async () => {
    const runtimeInfo = deferred<LlmRuntimeInfo>()
    vi.mocked(getLlmRuntime).mockReturnValue(runtimeInfo.promise)
    renderWorkspace()

    expect(await screen.findByRole('heading', { name: 'AdaCascade Workbench' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Local model', pressed: false })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'API model', pressed: false })).toBeDisabled()

    runtimeInfo.resolve(localRuntime)
    expect(await screen.findByRole('button', { name: 'Local model', pressed: true })).toBeEnabled()
  })

  it('shows runtime query errors with disabled and unselected runtime controls', async () => {
    vi.mocked(getLlmRuntime).mockRejectedValue(new Error('Runtime unavailable'))
    renderWorkspace()

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Runtime status is unavailable. Switching is disabled until it can be loaded.',
    )
    expect(screen.getByRole('button', { name: 'Local model', pressed: false })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'API model', pressed: false })).toBeDisabled()
  })

  it('fetches runtime info on load and displays the selected backend', async () => {
    vi.mocked(getLlmRuntime).mockResolvedValue(apiRuntime)
    renderWorkspace()

    await waitFor(() => expect(getLlmRuntime).toHaveBeenCalledWith('default'))
    expect(await screen.findByRole('button', { name: 'API model', pressed: true })).toBeEnabled()
    expect(screen.getByRole('button', { name: 'Local model', pressed: false })).toBeEnabled()
  })

  it('switches tenant and reloads tenant-scoped tables and runtime info', async () => {
    const user = userEvent.setup()
    renderWorkspace()

    expect(await screen.findByText('Default Tenant Table · 10 × 3')).toBeInTheDocument()

    await user.selectOptions(screen.getByLabelText('Tenant'), 'benchmark')

    await waitFor(() => expect(listTables).toHaveBeenCalledWith('benchmark'))
    await waitFor(() => expect(getLlmRuntime).toHaveBeenCalledWith('benchmark'))
    expect(await screen.findByText('Benchmark Tenant Table · 1,000 × 12')).toBeInTheDocument()
  })

  it('starts tasks with advanced parameter options', async () => {
    const user = userEvent.setup()
    renderWorkspace()

    expect(await screen.findByText('Default Tenant Table · 10 × 3')).toBeInTheDocument()
    await user.clear(screen.getByLabelText('L3 LLM threshold'))
    await user.type(screen.getByLabelText('L3 LLM threshold'), '0.3')
    await user.clear(screen.getByLabelText('Matcher top-k'))
    await user.type(screen.getByLabelText('Matcher top-k'), '5')
    await user.click(screen.getByRole('button', { name: 'Run AdaCascade' }))

    expect(startIntegrate).toHaveBeenCalledWith('default', 'default_table', {
      theta_1: 0.2,
      theta_2: 0.55,
      theta_3: 0.3,
      theta_match: 0.7,
      matcher_top_k: 5,
    })
  })

  it('starts tasks with fast execution options when demo fast profile is selected', async () => {
    const user = userEvent.setup()
    renderWorkspace()

    expect(await screen.findByText('Default Tenant Table · 10 × 3')).toBeInTheDocument()
    await user.selectOptions(screen.getByLabelText('Execution profile'), 'fast')
    await user.click(screen.getByRole('button', { name: 'Run AdaCascade' }))

    expect(startIntegrate).toHaveBeenCalledWith('default', 'default_table', {
      theta_1: 0.2,
      theta_2: 0.55,
      theta_3: 0.5,
      theta_match: 0.7,
      matcher_top_k: 3,
      llm_cache_enabled: true,
      llm_batch_size: 10,
      llm_concurrency: 24,
    })
  })

  it('starts tasks with JOIN tuned recall options when that profile is selected', async () => {
    const user = userEvent.setup()
    renderWorkspace()

    expect(await screen.findByText('Default Tenant Table · 10 × 3')).toBeInTheDocument()
    await user.selectOptions(screen.getByLabelText('Execution profile'), 'joinTuned')
    await user.click(screen.getByRole('button', { name: 'Run AdaCascade' }))

    expect(startIntegrate).toHaveBeenCalledWith('default', 'default_table', {
      theta_1: 0.2,
      theta_2: 0.55,
      theta_3: 0.5,
      theta_match: 0.7,
      matcher_top_k: 3,
      column_recall_enabled: true,
      column_recall_top_k: 10,
      column_recall_add_k: 10,
    })
  })

  it('defaults to light theme and persists root theme changes from the toolbar', async () => {
    const user = userEvent.setup()
    renderWorkspace()

    expect(await screen.findByRole('heading', { name: 'AdaCascade Workbench' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Light', pressed: true })).toBeEnabled()
    expect(document.documentElement).toHaveAttribute('data-theme', 'light')
    expect(window.localStorage.getItem('adacascade.theme')).toBeNull()

    await user.click(screen.getByRole('button', { name: 'Dark', pressed: false }))

    expect(screen.getByRole('button', { name: 'Dark', pressed: true })).toBeEnabled()
    expect(document.documentElement).toHaveAttribute('data-theme', 'dark')
    expect(window.localStorage.getItem('adacascade.theme')).toBe('dark')
  })

  it('applies a saved dark theme preference on load and cleans up on unmount', async () => {
    window.localStorage.setItem('adacascade.theme', 'dark')
    const { unmount } = renderWorkspace()

    expect(await screen.findByRole('heading', { name: 'AdaCascade Workbench' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Dark', pressed: true })).toBeEnabled()
    expect(document.documentElement).toHaveAttribute('data-theme', 'dark')

    unmount()

    expect(document.documentElement).not.toHaveAttribute('data-theme')
  })

  it('updates runtime backend through the API client and displays the response backend', async () => {
    const user = userEvent.setup()
    renderWorkspace()

    const apiButton = await screen.findByRole('button', { name: 'API model', pressed: false })
    await user.click(apiButton)

    expect(updateLlmRuntime).toHaveBeenCalledWith('default', 'api')
    expect(await screen.findByRole('button', { name: 'API model', pressed: true })).toBeEnabled()
    expect(screen.getByRole('button', { name: 'Local model', pressed: false })).toBeEnabled()
    expect(window.localStorage.getItem('adacascade.runtimeBackend')).toBeNull()
  })

  it('shows a runtime mutation error and preserves the previous selected backend', async () => {
    const user = userEvent.setup()
    vi.mocked(updateLlmRuntime).mockRejectedValue(new Error('Switch failed'))
    renderWorkspace()

    const apiButton = await screen.findByRole('button', { name: 'API model', pressed: false })
    await user.click(apiButton)

    expect(updateLlmRuntime).toHaveBeenCalledWith('default', 'api')
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Runtime switch failed. The previous backend is still selected.',
    )
    expect(screen.getByRole('button', { name: 'Local model', pressed: true })).toBeEnabled()
    expect(screen.getByRole('button', { name: 'API model', pressed: false })).toBeEnabled()
  })

  it('disables runtime switching while a task is running', async () => {
    useTaskStore.setState({ currentTaskId: 'task-running' })
    renderWorkspace()

    expect(await screen.findByRole('button', { name: 'Local model', pressed: true })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'API model', pressed: false })).toBeDisabled()
  })

  it('cancels the current running task from the control panel', async () => {
    const user = userEvent.setup()
    useTaskStore.setState({ currentTaskId: 'task-running' })
    renderWorkspace()

    await user.click(await screen.findByRole('button', { name: 'Cancel task' }))

    expect(cancelTask).toHaveBeenCalledWith('default', 'task-running')
    await waitFor(() => expect(getTask).toHaveBeenCalled())
  })

  it('disables runtime switching while runtime mutation is pending', async () => {
    const user = userEvent.setup()
    const runtimeUpdate = deferred<LlmRuntimeInfo>()
    vi.mocked(updateLlmRuntime).mockReturnValue(runtimeUpdate.promise)
    renderWorkspace()

    const apiButton = await screen.findByRole('button', { name: 'API model', pressed: false })
    await user.click(apiButton)

    expect(updateLlmRuntime).toHaveBeenCalledWith('default', 'api')
    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Local model', pressed: true })).toBeDisabled()
      expect(screen.getByRole('button', { name: 'Switching…', pressed: false })).toBeDisabled()
    })

    runtimeUpdate.resolve(apiRuntime)
    expect(await screen.findByRole('button', { name: 'API model', pressed: true })).toBeEnabled()
  })

  it('switches visible workspace copy and agent summaries after selecting Chinese', async () => {
    const user = userEvent.setup()
    renderWorkspace()

    expect(await screen.findByRole('heading', { name: 'AdaCascade Workbench' })).toBeInTheDocument()
    expect(screen.getByText('Builds the task plan and mode routing.')).toBeInTheDocument()
    expect(screen.getByText('Chooses discover, match, or integrate execution path.')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: '中文' }))

    expect(await screen.findByRole('heading', { name: 'AdaCascade 工作台' })).toBeInTheDocument()
    expect(screen.getByLabelText('本地演示安全提醒')).toHaveTextContent('本地演示环境')
    expect(screen.getByText('生成任务计划并选择模式路由。')).toBeInTheDocument()
    expect(screen.getByText('选择发现、匹配或集成执行路径。')).toBeInTheDocument()
    expect(window.localStorage.getItem('adacascade.language')).toBe('zh')
  })
})
