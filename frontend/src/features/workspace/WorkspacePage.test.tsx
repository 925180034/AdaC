import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
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
    vi.clearAllMocks()
    vi.mocked(listTables).mockResolvedValue(tablesResponse)
  })

  it('loads tables for the default tenant when no tenant is in the URL', async () => {
    renderWorkspace()

    await waitFor(() => expect(listTables).toHaveBeenCalledWith('default'))
    expect(await screen.findByText('Default Tenant Table · 10 × 3')).toBeInTheDocument()
  })
})
