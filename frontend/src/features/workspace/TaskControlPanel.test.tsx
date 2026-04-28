import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { TaskMode, TableSummary } from '../tasks/taskTypes'
import { TaskControlPanel } from './TaskControlPanel'

const tables: TableSummary[] = [
  {
    table_id: 'table_customers',
    tenant_id: 'demo',
    table_name: 'Customer Master',
    row_count: 1280,
    col_count: 12,
    status: 'READY',
  },
  {
    table_id: 'table_orders',
    tenant_id: 'demo',
    table_name: 'Order Events',
    row_count: 8840,
    col_count: 18,
    status: 'READY',
  },
]

const baseProps = {
  tenantId: 'demo',
  tables,
  queryTableId: 'table_customers',
  sourceTableId: 'table_customers',
  targetTableId: 'table_orders',
  isRunning: false,
  onModeChange: vi.fn(),
  onQueryTableChange: vi.fn(),
  onSourceTableChange: vi.fn(),
  onTargetTableChange: vi.fn(),
  onRun: vi.fn(),
}

describe('TaskControlPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders mode and table controls and Run AdaCascade button for discovery', () => {
    render(<TaskControlPanel {...baseProps} mode={'discover' satisfies TaskMode} />)

    expect(screen.getByRole('heading', { name: 'Task Control' })).toBeInTheDocument()
    expect(screen.getByLabelText('Mode')).toBeInTheDocument()
    expect(screen.getByLabelText('Query table')).toBeInTheDocument()
    expect(screen.queryByLabelText('Source table')).not.toBeInTheDocument()
    expect(screen.queryByLabelText('Target table')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Run AdaCascade' })).toBeEnabled()
  })

  it('renders source and target table controls for match mode', () => {
    render(<TaskControlPanel {...baseProps} mode={'match' satisfies TaskMode} />)

    expect(screen.getByLabelText('Mode')).toBeInTheDocument()
    expect(screen.queryByLabelText('Query table')).not.toBeInTheDocument()
    expect(screen.getByLabelText('Source table')).toBeInTheDocument()
    expect(screen.getByLabelText('Target table')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Run AdaCascade' })).toBeEnabled()
  })

  it('calls onModeChange when the mode select changes', async () => {
    const user = userEvent.setup()
    render(<TaskControlPanel {...baseProps} mode={'discover' satisfies TaskMode} />)

    await user.selectOptions(screen.getByLabelText('Mode'), 'match')

    expect(baseProps.onModeChange).toHaveBeenCalledTimes(1)
    expect(baseProps.onModeChange).toHaveBeenCalledWith('match')
  })

  it('calls onQueryTableChange when the query table select changes', async () => {
    const user = userEvent.setup()
    render(<TaskControlPanel {...baseProps} mode={'discover' satisfies TaskMode} />)

    await user.selectOptions(screen.getByLabelText('Query table'), 'table_orders')

    expect(baseProps.onQueryTableChange).toHaveBeenCalledTimes(1)
    expect(baseProps.onQueryTableChange).toHaveBeenCalledWith('table_orders')
  })

  it('disables Run AdaCascade and shows the running label while running', () => {
    render(<TaskControlPanel {...baseProps} mode={'integrate' satisfies TaskMode} isRunning />)

    expect(screen.getByRole('button', { name: 'Running AdaCascade…' })).toBeDisabled()
    expect(screen.queryByRole('button', { name: 'Run AdaCascade' })).not.toBeInTheDocument()
  })

  it('calls source and target table callbacks when match selects change', async () => {
    const user = userEvent.setup()
    render(
      <TaskControlPanel
        {...baseProps}
        mode={'match' satisfies TaskMode}
        sourceTableId="table_orders"
        targetTableId="table_customers"
      />,
    )

    await user.selectOptions(screen.getByLabelText('Source table'), 'table_customers')
    await user.selectOptions(screen.getByLabelText('Target table'), 'table_orders')

    expect(baseProps.onSourceTableChange).toHaveBeenCalledTimes(1)
    expect(baseProps.onSourceTableChange).toHaveBeenCalledWith('table_customers')
    expect(baseProps.onTargetTableChange).toHaveBeenCalledTimes(1)
    expect(baseProps.onTargetTableChange).toHaveBeenCalledWith('table_orders')
  })

  it('calls onRun when Run AdaCascade is clicked', async () => {
    const user = userEvent.setup()
    render(<TaskControlPanel {...baseProps} mode={'integrate' satisfies TaskMode} />)

    await user.click(screen.getByRole('button', { name: 'Run AdaCascade' }))

    expect(baseProps.onRun).toHaveBeenCalledTimes(1)
  })
})
