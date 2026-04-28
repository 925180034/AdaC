import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import userEvent from '@testing-library/user-event'
import { render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { ListTablesResponse } from '../../api/tables'
import { listTables } from '../../api/tables'
import { WorkspacePage } from './WorkspacePage'

vi.mock('../../api/tables', () => ({
  listTables: vi.fn(),
}))

vi.mock('../../api/events', () => ({
  subscribeTaskEvents: vi.fn(),
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

function renderWorkspace() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })

  return render(
    <QueryClientProvider client={queryClient}>
      <WorkspacePage />
    </QueryClientProvider>,
  )
}

describe('WorkspacePage', () => {
  beforeEach(() => {
    window.history.replaceState(null, '', '/')
    window.localStorage.clear()
    vi.clearAllMocks()
    vi.mocked(listTables).mockResolvedValue(tablesResponse)
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

  it('keeps page-level runtime and theme controls non-interactive before backend wiring', async () => {
    const user = userEvent.setup()
    renderWorkspace()

    expect(await screen.findByRole('heading', { name: 'AdaCascade Workbench' })).toBeInTheDocument()

    const lightButton = screen.getByRole('button', { name: 'Light', pressed: true })
    const darkButton = screen.getByRole('button', { name: 'Dark', pressed: false })
    const localButton = screen.getByRole('button', { name: 'Local model', pressed: true })
    const apiButton = screen.getByRole('button', { name: 'API model', pressed: false })

    expect(lightButton).toBeDisabled()
    expect(darkButton).toBeDisabled()
    expect(localButton).toBeDisabled()
    expect(apiButton).toBeDisabled()

    await user.click(darkButton)
    await user.click(apiButton)

    expect(screen.getByRole('button', { name: 'Light', pressed: true })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Dark', pressed: false })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Local model', pressed: true })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'API model', pressed: false })).toBeDisabled()
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
