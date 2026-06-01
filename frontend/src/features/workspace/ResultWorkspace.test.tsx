import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import type { TableSummary, TaskDetail } from '../tasks/taskTypes'
import { ResultWorkspace } from './ResultWorkspace'

const tables: TableSummary[] = [
  {
    table_id: 'query_customers',
    tenant_id: 'demo',
    dataset_id: 'dataset-demo',
    table_name: 'research_projects',
    row_count: 12,
    col_count: 8,
    status: 'READY',
  },
  {
    table_id: 'candidate_orders',
    tenant_id: 'demo',
    dataset_id: 'dataset-demo',
    table_name: 'subsidies',
    row_count: 14,
    col_count: 9,
    status: 'READY',
  },
]

const task: TaskDetail = {
  task_id: 'task-graph-1',
  tenant_id: 'demo',
  task_type: 'INTEGRATE',
  query_table_id: 'query_customers',
  target_table_id: null,
  status: 'SUCCESS',
  submitted_at: '2026-04-27T00:00:00Z',
  finished_at: '2026-04-27T00:00:01Z',
  error_message: null,
  plan_config: {},
  trace: [],
  ranking: [
    {
      rank: 1,
      candidate_table: 'candidate_orders',
      score: 0.91,
      layer_scores: { s1: 0.82, s2: 0.88, s3: 0.93 },
    },
  ],
  mappings: [
    {
      mapping_id: 'mapping-1',
      src_column_id: 'col_4f8a2b',
      tgt_column_id: 'col_9c1d7e',
      src_column_name: 'customer_name',
      tgt_column_name: 'buyer_name',
      scenario: 'SMD',
      confidence: 0.87,
      is_matched: true,
      reasoning: 'semantic match',
      created_at: '2026-04-27T00:00:01Z',
    },
  ],
}

describe('ResultWorkspace', () => {
  it('renders a result summary dashboard above the result tabs', () => {
    render(<ResultWorkspace task={task} />)

    const summary = screen.getByRole('region', { name: 'Result summary' })

    expect(summary).toHaveTextContent('INTEGRATE')
    expect(summary).toHaveTextContent('1s runtime')
    expect(summary).toHaveTextContent('1 candidate')
    expect(summary).toHaveTextContent('1 mapping')
    expect(summary).toHaveTextContent('demo')
  })

  it('uses an expanded no-task dashboard placeholder', () => {
    render(<ResultWorkspace task={null} />)

    expect(screen.getByRole('region', { name: 'Result dashboard placeholder' })).toHaveTextContent('No active task')
  })

  it('renders task graph canvas with readable table labels and legend', () => {
    render(<ResultWorkspace task={task} tables={tables} />)

    const graph = screen.getByRole('region', { name: 'Result graph' })

    expect(graph).toBeInTheDocument()
    expect(graph).toHaveClass('graph-canvas--large')
    expect(graph).toHaveTextContent('research_projects')
    expect(graph).toHaveTextContent('subsidies')
    expect(graph).toHaveTextContent('Table discovery')
    expect(graph).toHaveTextContent('Column mapping')
    expect(screen.queryByText('React Flow canvas reserved')).not.toBeInTheDocument()
  })

  it('preserves the no-task empty state without rendering a graph', () => {
    render(<ResultWorkspace task={null} />)

    expect(screen.getByText('No active task')).toBeInTheDocument()
    expect(screen.queryByRole('region', { name: 'Result graph' })).not.toBeInTheDocument()
  })

  it('renders Chinese empty state and result tabs when requested', async () => {
    const user = userEvent.setup()
    const { rerender } = render(<ResultWorkspace task={null} language="zh" />)

    expect(screen.getByRole('heading', { name: '结果工作区' })).toBeInTheDocument()
    expect(screen.getByText('暂无活跃任务')).toBeInTheDocument()

    rerender(<ResultWorkspace task={task} language="zh" />)
    await user.click(screen.getByRole('tab', { name: '候选排序' }))
    expect(screen.getByRole('tabpanel', { name: '候选排序' })).toHaveTextContent('1 个候选')
  })

  it('shows scenario badges and backend error details in results', async () => {
    const user = userEvent.setup()
    render(<ResultWorkspace task={{ ...task, status: 'FAILED', error_message: 'LLM timeout' }} />)

    expect(screen.getByRole('alert')).toHaveTextContent('LLM timeout')

    await user.click(screen.getByRole('tab', { name: 'Mappings' }))

    expect(screen.getByText('Scenario SMD')).toBeInTheDocument()
    expect(screen.getByText('customer_name')).toBeInTheDocument()
    expect(screen.getByText('buyer_name')).toBeInTheDocument()
    expect(screen.queryByText('col_4f8a2b')).not.toBeInTheDocument()
    expect(screen.queryByText('col_9c1d7e')).not.toBeInTheDocument()
    expect(screen.getByText('87%')).toBeInTheDocument()
  })

  it('explains why match-only tasks have no ranking rows', async () => {
    const user = userEvent.setup()
    render(<ResultWorkspace task={{ ...task, task_type: 'MATCH_ONLY', ranking: [] }} />)

    await user.click(screen.getByRole('tab', { name: 'Ranking' }))

    expect(screen.getByText('Match mode compares the selected source and target tables directly, so no discovery ranking is produced.')).toBeInTheDocument()
  })

  it('keeps long mapping labels inside cards and exposes full labels', async () => {
    const user = userEvent.setup()
    const longSource = 'farm_irrigation_sensor_calibration_measurement_timestamp'
    const longTarget = 'worker_assignment_field_operation_observation_timestamp'
    render(
      <ResultWorkspace
        task={{
          ...task,
          mappings: [
            {
              ...task.mappings[0],
              src_column_name: longSource,
              tgt_column_name: longTarget,
            },
          ],
        }}
        tables={tables}
      />,
    )

    const graph = screen.getByRole('region', { name: 'Result graph' })
    expect(within(graph).getByTitle(longSource)).toHaveClass('graph-node__label')
    expect(within(graph).getByTitle(longTarget)).toHaveClass('graph-node__label')

    await user.click(screen.getByRole('tab', { name: 'Mappings' }))
    const mappings = screen.getByRole('tabpanel', { name: 'Mappings' })
    expect(within(mappings).getByTitle(longSource)).toHaveClass('mapping-card__column')
    expect(within(mappings).getByTitle(longTarget)).toHaveClass('mapping-card__column')
  })

  it('switches between graph, ranking, mappings, and raw JSON result views', async () => {
    const user = userEvent.setup()
    render(<ResultWorkspace task={task} tables={tables} />)

    expect(screen.getByRole('region', { name: 'Result graph' })).toBeInTheDocument()
    expect(screen.queryByRole('region', { name: 'Ranking results' })).not.toBeInTheDocument()

    await user.click(screen.getByRole('tab', { name: 'Ranking' }))
    const ranking = screen.getByRole('tabpanel', { name: 'Ranking' })
    expect(within(ranking).getByText('subsidies')).toBeInTheDocument()
    expect(within(ranking).queryByText('candidate_orders')).not.toBeInTheDocument()
    expect(screen.queryByRole('region', { name: 'Result graph' })).not.toBeInTheDocument()

    await user.click(screen.getByRole('tab', { name: 'Mappings' }))
    const mappings = screen.getByRole('tabpanel', { name: 'Mappings' })
    expect(within(mappings).getByText('customer_name')).toBeInTheDocument()
    expect(within(mappings).getByText('buyer_name')).toBeInTheDocument()
    expect(within(mappings).queryByText('col_4f8a2b')).not.toBeInTheDocument()
    expect(screen.queryByRole('tabpanel', { name: 'Ranking' })).not.toBeInTheDocument()

    await user.click(screen.getByRole('tab', { name: 'Raw JSON' }))
    const rawJson = screen.getByRole('tabpanel', { name: 'Raw JSON' })
    expect(rawJson).toHaveTextContent('task-graph-1')

    await user.click(screen.getByRole('tab', { name: 'Graph' }))
    expect(screen.getByRole('region', { name: 'Result graph' })).toBeInTheDocument()
  })

  it('previews a ranking candidate table', async () => {
    const user = userEvent.setup()
    const onPreviewTable = vi.fn()
    render(<ResultWorkspace task={task} tables={tables} onPreviewTable={onPreviewTable} />)

    await user.click(screen.getByRole('tab', { name: 'Ranking' }))
    await user.click(screen.getByRole('button', { name: 'Preview subsidies' }))

    expect(onPreviewTable).toHaveBeenCalledTimes(1)
    expect(onPreviewTable).toHaveBeenCalledWith('candidate_orders')
  })

  it('previews mapping query and target tables', async () => {
    const user = userEvent.setup()
    const onPreviewTable = vi.fn()
    render(
      <ResultWorkspace
        task={{ ...task, target_table_id: 'candidate_orders' }}
        tables={tables}
        onPreviewTable={onPreviewTable}
      />,
    )

    await user.click(screen.getByRole('tab', { name: 'Mappings' }))
    await user.click(screen.getByRole('button', { name: 'Preview query table' }))
    await user.click(screen.getByRole('button', { name: 'Preview target table' }))

    expect(onPreviewTable).toHaveBeenCalledWith('query_customers')
    expect(onPreviewTable).toHaveBeenCalledWith('candidate_orders')
  })
})
