import { describe, expect, it } from 'vitest'
import { buildTaskGraph } from './graphModel'
import type { TableSummary, TaskDetail } from '../tasks/taskTypes'

const tableSummaries: TableSummary[] = [
  {
    table_id: 'query_table',
    tenant_id: 'default',
    dataset_id: 'dataset-demo',
    table_name: 'research_projects',
    row_count: 12,
    col_count: 8,
    status: 'READY',
  },
  {
    table_id: 'candidate_a',
    tenant_id: 'default',
    dataset_id: 'dataset-demo',
    table_name: 'subsidies',
    row_count: 14,
    col_count: 9,
    status: 'READY',
  },
]

const baseTask: TaskDetail = {
  task_id: 'task-1',
  tenant_id: 'default',
  task_type: 'INTEGRATE',
  query_table_id: 'query_table',
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
      candidate_table: 'candidate_a',
      score: 0.91,
      layer_scores: { s1: 0.8, s2: 0.9, s3: 0.95 },
    },
  ],
  mappings: [
    {
      mapping_id: 'mapping-1',
      src_column_id: 'src_name',
      tgt_column_id: 'tgt_name',
      scenario: 'SMD',
      confidence: 0.88,
      is_matched: true,
      reasoning: 'same semantic column',
      created_at: '2026-04-27T00:00:01Z',
    },
  ],
}

describe('buildTaskGraph', () => {
  it('maps ranking items to query and candidate table nodes with readable labels', () => {
    const graph = buildTaskGraph(baseTask, tableSummaries)

    expect(graph.nodes).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          id: 'table:query_table',
          kind: 'query_table',
          label: 'research_projects',
          table_id: 'query_table',
          meta: 'query_table',
        }),
        expect.objectContaining({
          id: 'table:candidate_a',
          kind: 'candidate_table',
          label: 'subsidies',
          table_id: 'candidate_a',
          meta: 'candidate_a',
        }),
      ]),
    )
    expect(graph.edges).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          id: 'discovery:query_table:candidate_a',
          kind: 'discovery',
          source: 'table:query_table',
          target: 'table:candidate_a',
          weight: 0.91,
          label: '#1 0.910',
          metrics: { s1: 0.8, s2: 0.9, s3: 0.95 },
        }),
      ]),
    )
  })

  it('maps mappings to source and target column nodes with readable labels', () => {
    const graph = buildTaskGraph({
      ...baseTask,
      mappings: [
        {
          ...baseTask.mappings[0],
          src_column_id: 'col_4f8a2b',
          tgt_column_id: 'col_9c1d7e',
          src_column_name: 'farmer_name',
          tgt_column_name: 'worker_name',
        },
      ],
    })

    expect(graph.nodes).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          id: 'column:col_4f8a2b',
          kind: 'source_column',
          label: 'farmer_name',
          meta: 'col_4f8a2b',
          column_id: 'col_4f8a2b',
        }),
        expect.objectContaining({
          id: 'column:col_9c1d7e',
          kind: 'target_column',
          label: 'worker_name',
          meta: 'col_9c1d7e',
          column_id: 'col_9c1d7e',
        }),
      ]),
    )
    expect(graph.edges).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          id: 'mapping:mapping-1',
          kind: 'mapping',
          source: 'column:col_4f8a2b',
          target: 'column:col_9c1d7e',
          weight: 0.88,
          label: '0.880',
          scenario: 'SMD',
          explanation: 'same semantic column',
        }),
      ]),
    )
  })
})
