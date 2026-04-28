import { describe, expect, it } from 'vitest'
import { buildTaskGraph } from './graphModel'
import type { TaskDetail } from '../tasks/taskTypes'

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
  it('maps ranking items to query and candidate table nodes with discovery edges', () => {
    const graph = buildTaskGraph(baseTask)

    expect(graph.nodes).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          id: 'table:query_table',
          kind: 'query_table',
          label: 'query_table',
          table_id: 'query_table',
        }),
        expect.objectContaining({
          id: 'table:candidate_a',
          kind: 'candidate_table',
          label: 'candidate_a',
          table_id: 'candidate_a',
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

  it('maps mappings to source and target column nodes with mapping edges', () => {
    const graph = buildTaskGraph(baseTask)

    expect(graph.nodes).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          id: 'column:src_name',
          kind: 'source_column',
          label: 'src_name',
          column_id: 'src_name',
        }),
        expect.objectContaining({
          id: 'column:tgt_name',
          kind: 'target_column',
          label: 'tgt_name',
          column_id: 'tgt_name',
        }),
      ]),
    )
    expect(graph.edges).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          id: 'mapping:mapping-1',
          kind: 'mapping',
          source: 'column:src_name',
          target: 'column:tgt_name',
          weight: 0.88,
          label: '0.880',
          scenario: 'SMD',
          explanation: 'same semantic column',
        }),
      ]),
    )
  })
})
