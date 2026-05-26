import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { TaskMode, TableSummary } from '../tasks/taskTypes'
import { TaskControlPanel } from './TaskControlPanel'
import { PAPER_PARAMETER_DEFAULTS } from './parameters'

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
  tenantId: 'default',
  tenantOptions: [
    { value: 'default', label: 'default (demo)' },
    { value: 'benchmark', label: 'benchmark (full)' },
  ],
  executionProfile: 'reproducible' as const,
  parameters: PAPER_PARAMETER_DEFAULTS,
  tables,
  queryTableId: 'table_customers',
  sourceTableId: 'table_customers',
  targetTableId: 'table_orders',
  isRunning: false,
  canRun: true,
  onTenantChange: vi.fn(),
  onExecutionProfileChange: vi.fn(),
  onParameterChange: vi.fn(),
  onResetParameters: vi.fn(),
  onModeChange: vi.fn(),
  onQueryTableChange: vi.fn(),
  onSourceTableChange: vi.fn(),
  onTargetTableChange: vi.fn(),
  onRun: vi.fn(),
  onCancel: vi.fn(),
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

  it('renders Chinese copy when the workspace language is Chinese', () => {
    render(<TaskControlPanel {...baseProps} mode={'discover' satisfies TaskMode} language="zh" />)

    expect(screen.getByRole('heading', { name: '任务控制' })).toBeInTheDocument()
    expect(screen.getByLabelText('模式')).toBeInTheDocument()
    expect(screen.getByLabelText('查询表')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '运行 AdaCascade' })).toBeEnabled()
  })

  it('calls onTenantChange when the tenant select changes', async () => {
    const user = userEvent.setup()
    render(<TaskControlPanel {...baseProps} mode={'discover' satisfies TaskMode} />)

    await user.selectOptions(screen.getByLabelText('Tenant'), 'benchmark')

    expect(baseProps.onTenantChange).toHaveBeenCalledTimes(1)
    expect(baseProps.onTenantChange).toHaveBeenCalledWith('benchmark')
  })

  it('calls onExecutionProfileChange when the execution profile changes', async () => {
    const user = userEvent.setup()
    render(<TaskControlPanel {...baseProps} mode={'discover' satisfies TaskMode} />)

    await user.selectOptions(screen.getByLabelText('Execution profile'), 'joinTuned')

    expect(baseProps.onExecutionProfileChange).toHaveBeenCalledTimes(1)
    expect(baseProps.onExecutionProfileChange).toHaveBeenCalledWith('joinTuned')
  })

  it('keeps advanced parameters collapsed until requested', async () => {
    const user = userEvent.setup()
    render(<TaskControlPanel {...baseProps} mode={'discover' satisfies TaskMode} />)

    expect(screen.getByRole('button', { name: 'Show advanced parameters' })).toHaveAttribute('aria-expanded', 'false')
    expect(screen.queryByRole('group', { name: 'Advanced parameters' })).not.toBeInTheDocument()
    expect(screen.queryByLabelText('L1 threshold')).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Show advanced parameters' }))

    expect(screen.getByRole('button', { name: 'Hide advanced parameters' })).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getByRole('group', { name: 'Advanced parameters' })).toBeInTheDocument()
    expect(screen.getByLabelText('L1 threshold')).toHaveValue('0.2')
    expect(screen.getByLabelText('L2 threshold')).toHaveValue('0.55')
    expect(screen.getByLabelText('L3 LLM threshold')).toHaveValue('0.5')
    expect(screen.getByLabelText('Matcher threshold')).toHaveValue('0.7')
    expect(screen.getByLabelText('Matcher top-k')).toHaveValue('3')
    expect(screen.getByRole('button', { name: 'Reset to paper defaults' })).toBeEnabled()
  })

  it('updates advanced parameters and resets them to paper defaults', async () => {
    const user = userEvent.setup()
    render(<TaskControlPanel {...baseProps} mode={'discover' satisfies TaskMode} />)

    await user.click(screen.getByRole('button', { name: 'Show advanced parameters' }))
    await user.clear(screen.getByLabelText('L3 LLM threshold'))
    await user.type(screen.getByLabelText('L3 LLM threshold'), '0.3')
    await user.clear(screen.getByLabelText('Matcher top-k'))
    await user.type(screen.getByLabelText('Matcher top-k'), '5')
    await user.click(screen.getByRole('button', { name: 'Reset to paper defaults' }))

    expect(baseProps.onParameterChange).toHaveBeenCalledWith('theta_3', 0.3)
    expect(baseProps.onParameterChange).toHaveBeenCalledWith('matcher_top_k', 5)
    expect(baseProps.onResetParameters).toHaveBeenCalledTimes(1)
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

  it('disables tenant, profile, and Run AdaCascade while running', () => {
    render(<TaskControlPanel {...baseProps} mode={'integrate' satisfies TaskMode} isRunning canRun={false} />)

    expect(screen.getByLabelText('Tenant')).toBeDisabled()
    expect(screen.getByLabelText('Execution profile')).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Running AdaCascade…' })).toBeDisabled()
    expect(screen.queryByRole('button', { name: 'Run AdaCascade' })).not.toBeInTheDocument()
  })

  it('calls onCancel from a visible cancel button while running', async () => {
    const user = userEvent.setup()
    render(<TaskControlPanel {...baseProps} mode={'integrate' satisfies TaskMode} isRunning canRun={false} />)

    await user.click(screen.getByRole('button', { name: 'Cancel task' }))

    expect(baseProps.onCancel).toHaveBeenCalledTimes(1)
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

  it('previews the query table for discover and integrate modes', async () => {
    const user = userEvent.setup()
    const onPreviewTable = vi.fn()
    const { rerender } = render(
      <TaskControlPanel {...baseProps} mode={'discover' satisfies TaskMode} onPreviewTable={onPreviewTable} />,
    )

    await user.click(screen.getByRole('button', { name: 'Preview query table' }))
    expect(onPreviewTable).toHaveBeenCalledWith('table_customers')

    rerender(<TaskControlPanel {...baseProps} mode={'integrate' satisfies TaskMode} onPreviewTable={onPreviewTable} />)
    await user.click(screen.getByRole('button', { name: 'Preview query table' }))
    expect(onPreviewTable).toHaveBeenCalledWith('table_customers')
  })

  it('previews source and target tables for match mode', async () => {
    const user = userEvent.setup()
    const onPreviewTable = vi.fn()
    render(<TaskControlPanel {...baseProps} mode={'match' satisfies TaskMode} onPreviewTable={onPreviewTable} />)

    await user.click(screen.getByRole('button', { name: 'Preview source table' }))
    await user.click(screen.getByRole('button', { name: 'Preview target table' }))

    expect(onPreviewTable).toHaveBeenCalledWith('table_customers')
    expect(onPreviewTable).toHaveBeenCalledWith('table_orders')
  })

  it('disables preview controls without a handler or current table id', () => {
    const { rerender } = render(<TaskControlPanel {...baseProps} mode={'discover' satisfies TaskMode} />)

    expect(screen.getByRole('button', { name: 'Preview query table' })).toBeDisabled()

    rerender(
      <TaskControlPanel
        {...baseProps}
        mode={'discover' satisfies TaskMode}
        queryTableId="missing_table"
        onPreviewTable={vi.fn()}
      />,
    )

    expect(screen.getByRole('button', { name: 'Preview query table' })).toBeDisabled()
  })
})
