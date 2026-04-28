import { render, screen } from '@testing-library/react'
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
})
