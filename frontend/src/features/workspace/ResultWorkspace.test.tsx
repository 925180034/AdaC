import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import type { TaskDetail } from '../tasks/taskTypes'
import { ResultWorkspace } from './ResultWorkspace'

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
      src_column_id: 'customer_name',
      tgt_column_id: 'buyer_name',
      scenario: 'SMD',
      confidence: 0.87,
      is_matched: true,
      reasoning: 'semantic match',
      created_at: '2026-04-27T00:00:01Z',
    },
  ],
}

describe('ResultWorkspace', () => {
  it('renders task graph canvas from task result data', () => {
    render(<ResultWorkspace task={task} />)

    const graph = screen.getByRole('region', { name: 'Result graph' })

    expect(graph).toBeInTheDocument()
    expect(graph).toHaveTextContent('query_customers')
    expect(graph).toHaveTextContent('candidate_orders')
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
    await user.click(screen.getByRole('tab', { name: '排序' }))
    expect(screen.getByRole('tabpanel', { name: '排序' })).toHaveTextContent('1 个候选')
  })

  it('switches between graph, ranking, mappings, and raw JSON result views', async () => {
    const user = userEvent.setup()
    render(<ResultWorkspace task={task} />)

    expect(screen.getByRole('region', { name: 'Result graph' })).toBeInTheDocument()
    expect(screen.queryByRole('region', { name: 'Ranking results' })).not.toBeInTheDocument()

    await user.click(screen.getByRole('tab', { name: 'Ranking' }))
    const ranking = screen.getByRole('tabpanel', { name: 'Ranking' })
    expect(within(ranking).getByText('candidate_orders')).toBeInTheDocument()
    expect(screen.queryByRole('region', { name: 'Result graph' })).not.toBeInTheDocument()

    await user.click(screen.getByRole('tab', { name: 'Mappings' }))
    const mappings = screen.getByRole('tabpanel', { name: 'Mappings' })
    expect(within(mappings).getByText('customer_name')).toBeInTheDocument()
    expect(screen.queryByRole('tabpanel', { name: 'Ranking' })).not.toBeInTheDocument()

    await user.click(screen.getByRole('tab', { name: 'Raw JSON' }))
    const rawJson = screen.getByRole('tabpanel', { name: 'Raw JSON' })
    expect(rawJson).toHaveTextContent('task-graph-1')

    await user.click(screen.getByRole('tab', { name: 'Graph' }))
    expect(screen.getByRole('region', { name: 'Result graph' })).toBeInTheDocument()
  })
})
