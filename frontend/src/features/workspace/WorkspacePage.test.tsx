import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import userEvent from '@testing-library/user-event'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createDataset, listDatasets, uploadDatasetTables } from '../../api/datasets'
import type { DatasetSummary, ListDatasetsResponse } from '../../api/datasets'
import type { LlmRuntimeInfo } from '../../api/runtime'
import { getLlmRuntime, updateLlmRuntime } from '../../api/runtime'
import type { ListTablesResponse, TablePreviewResponse } from '../../api/tables'
import { getTablePreview, listTables } from '../../api/tables'
import { cancelTask, getTask, startDiscover, startIntegrate } from '../../api/tasks'
import { useTaskStore } from '../tasks/taskStore'
import type { TaskDetail } from '../tasks/taskTypes'
import { WorkspacePage } from './WorkspacePage'

vi.mock('../../api/datasets', () => ({
  createDataset: vi.fn(),
  listDatasets: vi.fn(),
  uploadDatasetTables: vi.fn(),
}))

vi.mock('../../api/runtime', () => ({
  getLlmRuntime: vi.fn(),
  updateLlmRuntime: vi.fn(),
}))

vi.mock('../../api/tables', () => ({
  getTablePreview: vi.fn(),
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

const defaultDataset: DatasetSummary = {
  dataset_id: 'dataset-default',
  dataset_name: 'Default Dataset',
  description: null,
  is_system: false,
  table_count: 1,
  ready_count: 1,
  failed_count: 0,
  created_at: '2026-05-16T00:00:00Z',
  updated_at: '2026-05-16T00:00:00Z',
}

const secondDataset: DatasetSummary = {
  dataset_id: 'dataset-second',
  dataset_name: 'Second Dataset',
  description: null,
  is_system: false,
  table_count: 1,
  ready_count: 1,
  failed_count: 0,
  created_at: '2026-05-16T00:00:00Z',
  updated_at: '2026-05-16T00:00:00Z',
}

const benchmarkDataset: DatasetSummary = {
  dataset_id: 'dataset-benchmark',
  dataset_name: 'Benchmark Dataset',
  description: null,
  is_system: true,
  table_count: 1,
  ready_count: 1,
  failed_count: 0,
  created_at: '2026-05-16T00:00:00Z',
  updated_at: '2026-05-16T00:00:00Z',
}

const datasetsResponse: ListDatasetsResponse = { items: [defaultDataset] }
const benchmarkDatasetsResponse: ListDatasetsResponse = { items: [benchmarkDataset] }

const defaultTable = {
  table_id: 'default_table',
  tenant_id: 'default',
  dataset_id: 'dataset-default',
  table_name: 'Default Tenant Table',
  row_count: 10,
  col_count: 3,
  status: 'READY' as const,
}

const tablesResponse: ListTablesResponse = {
  total: 1,
  offset: 0,
  limit: 200,
  items: [defaultTable],
}

const defaultTablePreview: TablePreviewResponse = {
  table: defaultTable,
  columns: ['id', 'name', 'score'],
  sample_rows: [{ id: 1, name: 'Ada', score: 0.98 }],
  sample_limit: 20,
}

const secondTablesResponse: ListTablesResponse = {
  total: 1,
  offset: 0,
  limit: 200,
  items: [
    {
      table_id: 'second_table',
      tenant_id: 'default',
      dataset_id: 'dataset-second',
      table_name: 'Second Dataset Table',
      row_count: 20,
      col_count: 4,
      status: 'READY',
    },
  ],
}

const secondTablesChangedResponse: ListTablesResponse = {
  total: 1,
  offset: 0,
  limit: 200,
  items: [
    {
      table_id: 'second_table_refetched',
      tenant_id: 'default',
      dataset_id: 'dataset-second',
      table_name: 'Second Dataset Refetched Table',
      row_count: 30,
      col_count: 5,
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
      dataset_id: 'dataset-benchmark',
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
    vi.mocked(listDatasets).mockImplementation((tenantId) =>
      Promise.resolve(tenantId === 'benchmark' ? benchmarkDatasetsResponse : datasetsResponse),
    )
    vi.mocked(createDataset).mockResolvedValue({ ...defaultDataset, dataset_id: 'dataset-new', dataset_name: 'New Lake' })
    vi.mocked(uploadDatasetTables).mockResolvedValue({ dataset_id: 'dataset-default', accepted: [], rejected: [], skipped: [] })
    vi.mocked(listTables).mockImplementation((tenantId) =>
      Promise.resolve(tenantId === 'benchmark' ? benchmarkTablesResponse : tablesResponse),
    )
    vi.mocked(getTablePreview).mockResolvedValue(defaultTablePreview)
    vi.mocked(getLlmRuntime).mockResolvedValue(localRuntime)
    vi.mocked(updateLlmRuntime).mockResolvedValue(apiRuntime)
    vi.mocked(getTask).mockResolvedValue(runningTask)
    vi.mocked(cancelTask).mockResolvedValue({ ...runningTask, status: 'FAILED', error_message: 'Task cancelled by user' })
    vi.mocked(startIntegrate).mockResolvedValue({ task_id: 'task-running', status: 'RUNNING', state: {} })
    vi.mocked(startDiscover).mockResolvedValue({ task_id: 'task-running', status: 'RUNNING', state: {} })
  })

  it('loads tables for the default tenant when no tenant is in the URL', async () => {
    renderWorkspace()

    await waitFor(() => expect(listTables).toHaveBeenCalledWith('default', 'dataset-default'))
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

  it('switches tenant and reloads tenant-scoped Datasets, tables, and runtime info', async () => {
    const user = userEvent.setup()
    renderWorkspace()

    expect(await screen.findByText('Default Tenant Table · 10 × 3')).toBeInTheDocument()

    await user.selectOptions(screen.getByLabelText('Tenant'), 'benchmark')

    await waitFor(() => expect(listDatasets).toHaveBeenCalledWith('benchmark'))
    await waitFor(() => expect(listTables).toHaveBeenCalledWith('benchmark', 'dataset-benchmark'))
    await waitFor(() => expect(getLlmRuntime).toHaveBeenCalledWith('benchmark'))
    expect(await screen.findByText('Benchmark Tenant Table · 1,000 × 12')).toBeInTheDocument()
  })

  it('keeps Dataset upload controls collapsed until requested', async () => {
    const user = userEvent.setup()
    renderWorkspace()

    await screen.findByText('Default Tenant Table · 10 × 3')

    expect(screen.getByLabelText('Dataset')).toBeInTheDocument()
    expect(screen.getByLabelText('Dataset table counts')).toHaveTextContent('Tables')
    expect(screen.queryByLabelText('Dataset name')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Files')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Show Dataset tools' })).toHaveAttribute('aria-expanded', 'false')

    await user.click(screen.getByRole('button', { name: 'Show Dataset tools' }))

    expect(screen.getByRole('button', { name: 'Hide Dataset tools' })).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getByLabelText('Dataset name')).toBeInTheDocument()
    expect(screen.getByLabelText('Files')).toBeInTheDocument()
  })

  it('creates a Dataset from the Dataset panel', async () => {
    const user = userEvent.setup()
    renderWorkspace()

    await screen.findByRole('heading', { name: 'Dataset Panel' })
    await user.click(screen.getByRole('button', { name: 'Show Dataset tools' }))
    await user.type(screen.getByLabelText('Dataset name'), 'New Lake')
    await user.type(screen.getByLabelText('Description'), 'demo')
    await user.click(screen.getByRole('button', { name: 'Create Dataset' }))

    expect(createDataset).toHaveBeenCalledWith('default', { dataset_name: 'New Lake', description: 'demo' })
  })

  it('uploads files into the selected Dataset', async () => {
    const user = userEvent.setup()
    renderWorkspace()

    await screen.findByText('Default Tenant Table · 10 × 3')
    await user.click(screen.getByRole('button', { name: 'Show Dataset tools' }))
    const file = new File(['id,name\n1,Ada\n'], 'people.csv', { type: 'text/csv' })
    await user.upload(screen.getByLabelText('Files'), file)
    await user.type(screen.getByLabelText('Uploaded by'), 'tester')
    await user.click(screen.getByRole('button', { name: 'Upload to Dataset' }))

    expect(uploadDatasetTables).toHaveBeenCalledWith('default', 'dataset-default', [file], {
      uploadedBy: 'tester',
      tableNamePrefix: undefined,
    })
  })

  it('allows selecting a folder of files for upload', async () => {
    const user = userEvent.setup()
    renderWorkspace()

    await screen.findByText('Default Tenant Table · 10 × 3')
    await user.click(screen.getByRole('button', { name: 'Show Dataset tools' }))

    expect(screen.getByLabelText('Folder')).toHaveAttribute('webkitdirectory', '')
  })

  it('uploads dropped files into the selected Dataset', async () => {
    const user = userEvent.setup()
    renderWorkspace()

    await screen.findByText('Default Tenant Table · 10 × 3')
    await user.click(screen.getByRole('button', { name: 'Show Dataset tools' }))
    const file = new File(['id,name\n1,Ada\n'], 'people.csv', { type: 'text/csv' })
    await user.type(screen.getByLabelText('Uploaded by'), 'tester')
    fireEvent.drop(screen.getByLabelText('Drop files or folders'), {
      dataTransfer: {
        files: [file],
        items: [],
      },
    })
    await user.click(screen.getByRole('button', { name: 'Upload to Dataset' }))

    expect(uploadDatasetTables).toHaveBeenCalledWith('default', 'dataset-default', [file], {
      uploadedBy: 'tester',
      tableNamePrefix: undefined,
    })
  })

  it('disables Run while switched Dataset cached tables are refetching', async () => {
    const user = userEvent.setup()
    const secondTablesRefetch = deferred<ListTablesResponse>()
    let secondDatasetCalls = 0
    vi.mocked(listDatasets).mockResolvedValue({ items: [defaultDataset, secondDataset] })
    vi.mocked(listTables).mockImplementation((_tenantId, datasetId) => {
      if (datasetId === 'dataset-second') {
        secondDatasetCalls += 1
        return secondDatasetCalls === 1 ? Promise.resolve(secondTablesResponse) : secondTablesRefetch.promise
      }
      return Promise.resolve(tablesResponse)
    })
    renderWorkspace()

    expect(await screen.findByText('Default Tenant Table · 10 × 3')).toBeInTheDocument()
    await user.selectOptions(screen.getByLabelText('Dataset'), 'dataset-second')
    expect(await screen.findByText('Second Dataset Table · 20 × 4')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Run AdaCascade' })).toBeEnabled()

    await user.selectOptions(screen.getByLabelText('Dataset'), 'dataset-default')
    expect(await screen.findByText('Default Tenant Table · 10 × 3')).toBeInTheDocument()
    await user.selectOptions(screen.getByLabelText('Dataset'), 'dataset-second')

    expect(screen.getByText('Second Dataset Table · 20 × 4')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Run AdaCascade' })).toBeDisabled()

    secondTablesRefetch.resolve(secondTablesChangedResponse)
    expect(await screen.findByText('Second Dataset Refetched Table · 30 × 5')).toBeInTheDocument()
    await waitFor(() => expect(screen.getByRole('button', { name: 'Run AdaCascade' })).toBeEnabled())

    await user.click(screen.getByRole('button', { name: 'Run AdaCascade' }))
    expect(startIntegrate).toHaveBeenCalledWith(
      'default',
      'second_table_refetched',
      {
        theta_1: 0.2,
        theta_2: 0.55,
        theta_3: 0.5,
        theta_match: 0.7,
        matcher_top_k: 3,
      },
      'dataset-second',
    )
  })

  it('opens a table preview from task control and loads modal content', async () => {
    const user = userEvent.setup()
    renderWorkspace()

    expect(await screen.findByText('Default Tenant Table · 10 × 3')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Preview query table' }))

    expect(await screen.findByRole('dialog', { name: 'Table preview' })).toHaveTextContent('Default Tenant Table')
    expect(screen.getByRole('table', { name: 'Sample rows' })).toHaveTextContent('Ada')
    expect(getTablePreview).toHaveBeenCalledWith('default', 'default_table', 'dataset-default')
  })

  it('closes an open table preview when switching Datasets', async () => {
    const user = userEvent.setup()
    vi.mocked(listDatasets).mockResolvedValue({ items: [defaultDataset, secondDataset] })
    vi.mocked(listTables).mockImplementation((_tenantId, datasetId) => {
      if (datasetId === 'dataset-second') return Promise.resolve(secondTablesResponse)
      return Promise.resolve(tablesResponse)
    })
    renderWorkspace()

    expect(await screen.findByText('Default Tenant Table · 10 × 3')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Preview query table' }))
    expect(await screen.findByRole('dialog', { name: 'Table preview' })).toBeInTheDocument()

    await user.selectOptions(screen.getByLabelText('Dataset'), 'dataset-second')

    await waitFor(() => expect(screen.queryByRole('dialog', { name: 'Table preview' })).not.toBeInTheDocument())
  })

  it('uploads files from a dropped folder into the selected Dataset', async () => {
    const user = userEvent.setup()
    renderWorkspace()

    await screen.findByText('Default Tenant Table · 10 × 3')
    await user.click(screen.getByRole('button', { name: 'Show Dataset tools' }))
    const file = new File(['id,name\n1,Ada\n'], 'people.csv', { type: 'text/csv' })
    const fileEntry = {
      isFile: true,
      isDirectory: false,
      file: (callback: (droppedFile: File) => void) => callback(file),
    }
    const directoryEntry = {
      isFile: false,
      isDirectory: true,
      createReader: () => ({
        readEntries: (callback: (entries: typeof fileEntry[]) => void) => callback([fileEntry]),
      }),
    }

    await user.type(screen.getByLabelText('Uploaded by'), 'tester')
    fireEvent.drop(screen.getByLabelText('Drop files or folders'), {
      dataTransfer: {
        files: [],
        items: [{ webkitGetAsEntry: () => directoryEntry }],
      },
    })
    await screen.findByText('1 selected')
    await user.click(screen.getByRole('button', { name: 'Upload to Dataset' }))

    expect(uploadDatasetTables).toHaveBeenCalledWith('default', 'dataset-default', [file], {
      uploadedBy: 'tester',
      tableNamePrefix: undefined,
    })
  })

  it('starts tasks with advanced parameter options', async () => {
    const user = userEvent.setup()
    renderWorkspace()

    expect(await screen.findByText('Default Tenant Table · 10 × 3')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Show advanced parameters' }))
    await user.clear(screen.getByLabelText('L3 LLM threshold'))
    await user.type(screen.getByLabelText('L3 LLM threshold'), '0.3')
    await user.clear(screen.getByLabelText('Matcher top-k'))
    await user.type(screen.getByLabelText('Matcher top-k'), '5')
    await user.click(screen.getByRole('button', { name: 'Run AdaCascade' }))

    expect(startIntegrate).toHaveBeenCalledWith(
      'default',
      'default_table',
      {
        theta_1: 0.2,
        theta_2: 0.55,
        theta_3: 0.3,
        theta_match: 0.7,
        matcher_top_k: 5,
      },
      'dataset-default',
    )
  })

  it('starts tasks with fast execution options when demo fast profile is selected', async () => {
    const user = userEvent.setup()
    renderWorkspace()

    expect(await screen.findByText('Default Tenant Table · 10 × 3')).toBeInTheDocument()
    await user.selectOptions(screen.getByLabelText('Execution profile'), 'fast')
    await user.click(screen.getByRole('button', { name: 'Run AdaCascade' }))

    expect(startIntegrate).toHaveBeenCalledWith(
      'default',
      'default_table',
      {
        theta_1: 0.2,
        theta_2: 0.55,
        theta_3: 0.5,
        theta_match: 0.7,
        matcher_top_k: 3,
        llm_cache_enabled: true,
        llm_batch_size: 10,
        llm_concurrency: 24,
        matcher_llm_concurrency: 8,
      },
      'dataset-default',
    )
  })

  it('starts tasks with JOIN tuned recall options when that profile is selected', async () => {
    const user = userEvent.setup()
    renderWorkspace()

    expect(await screen.findByText('Default Tenant Table · 10 × 3')).toBeInTheDocument()
    await user.selectOptions(screen.getByLabelText('Execution profile'), 'joinTuned')
    await user.click(screen.getByRole('button', { name: 'Run AdaCascade' }))

    expect(startIntegrate).toHaveBeenCalledWith(
      'default',
      'default_table',
      {
        theta_1: 0.2,
        theta_2: 0.55,
        theta_3: 0.5,
        theta_match: 0.7,
        matcher_top_k: 3,
        column_recall_enabled: true,
        column_recall_top_k: 10,
        column_recall_add_k: 10,
        matcher_llm_concurrency: 8,
      },
      'dataset-default',
    )
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
