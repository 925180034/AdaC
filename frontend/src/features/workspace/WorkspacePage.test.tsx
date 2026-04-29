import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import userEvent from '@testing-library/user-event'
import { render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { LlmRuntimeInfo } from '../../api/runtime'
import { getLlmRuntime, updateLlmRuntime } from '../../api/runtime'
import type { ListTablesResponse } from '../../api/tables'
import { listTables } from '../../api/tables'
import { getTask, startIntegrate } from '../../api/tasks'
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
    vi.clearAllMocks()
    useTaskStore.setState({ currentTaskId: null, events: [] })
    vi.mocked(listTables).mockResolvedValue(tablesResponse)
    vi.mocked(getLlmRuntime).mockResolvedValue(localRuntime)
    vi.mocked(updateLlmRuntime).mockResolvedValue(apiRuntime)
    vi.mocked(getTask).mockResolvedValue(runningTask)
    vi.mocked(startIntegrate).mockResolvedValue({ task_id: 'task-running', status: 'RUNNING', state: {} })
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

  it('keeps page-level theme controls non-interactive while runtime is enabled after loading', async () => {
    const user = userEvent.setup()
    renderWorkspace()

    expect(await screen.findByRole('heading', { name: 'AdaCascade Workbench' })).toBeInTheDocument()
    expect(await screen.findByRole('button', { name: 'Local model', pressed: true })).toBeEnabled()

    const lightButton = screen.getByRole('button', { name: 'Light', pressed: true })
    const darkButton = screen.getByRole('button', { name: 'Dark', pressed: false })

    expect(lightButton).toBeDisabled()
    expect(darkButton).toBeDisabled()

    await user.click(darkButton)

    expect(screen.getByRole('button', { name: 'Light', pressed: true })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Dark', pressed: false })).toBeDisabled()
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
