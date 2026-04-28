import { describe, expect, it } from 'vitest'
import { INITIAL_TIMELINE, applyTaskEvent } from './timeline'
import type { TaskEvent } from './taskTypes'

describe('applyTaskEvent', () => {
  it('marks a retrieval layer as running then success and records output size', () => {
    const started: TaskEvent = {
      task_id: 'task-1',
      type: 'agent_started',
      agent: 'Retrieval',
      layer: 'L1',
      timestamp: '2026-04-27T00:00:00Z',
    }
    const completed: TaskEvent = {
      task_id: 'task-1',
      type: 'agent_completed',
      agent: 'Retrieval',
      layer: 'L1',
      output_size: 80,
      timestamp: '2026-04-27T00:00:01Z',
    }

    const running = applyTaskEvent(INITIAL_TIMELINE, started)
    expect(running['Retrieval:L1'].status).toBe('running')

    const success = applyTaskEvent(running, completed)
    expect(success['Retrieval:L1']).toMatchObject({ status: 'success', output_size: 80 })
  })

  it('marks retrieval layer degraded events as degraded with reason', () => {
    const degraded = applyTaskEvent(INITIAL_TIMELINE, {
      task_id: 'task-1',
      type: 'agent_degraded',
      agent: 'Retrieval',
      layer: 'L2',
      reason: 'qdrant down',
      timestamp: '2026-04-27T00:00:00Z',
    })

    expect(degraded['Retrieval:L2']).toMatchObject({ status: 'degraded', reason: 'qdrant down' })
  })

  it('ignores layerless Retrieval events without creating a Retrieval node', () => {
    const updated = applyTaskEvent(INITIAL_TIMELINE, {
      task_id: 'task-1',
      type: 'agent_started',
      agent: 'Retrieval',
      timestamp: '2026-04-27T00:00:00Z',
    })

    expect(updated).toBe(INITIAL_TIMELINE)
    expect(updated).not.toHaveProperty('Retrieval')
  })

  it('ignores unknown Retrieval layers without creating an ad-hoc node', () => {
    const updated = applyTaskEvent(INITIAL_TIMELINE, {
      task_id: 'task-1',
      type: 'agent_started',
      agent: 'Retrieval',
      layer: 'L9',
      timestamp: '2026-04-27T00:00:00Z',
    })

    expect(updated).toBe(INITIAL_TIMELINE)
    expect(updated).not.toHaveProperty('Retrieval:L9')
  })

  it('preserves previous metrics when a later event omits them', () => {
    const withMetrics = applyTaskEvent(INITIAL_TIMELINE, {
      task_id: 'task-1',
      type: 'agent_started',
      agent: 'Matcher',
      layer: 'LLM',
      input_size: 0,
      output_size: 12,
      latency_ms: 150,
      llm_tokens: 42,
      timestamp: '2026-04-27T00:00:00Z',
    })

    const completed = applyTaskEvent(withMetrics, {
      task_id: 'task-1',
      type: 'agent_completed',
      agent: 'Matcher',
      layer: 'LLM',
      timestamp: '2026-04-27T00:00:01Z',
    })

    expect(completed['Matcher:LLM']).toMatchObject({
      status: 'success',
      input_size: 0,
      output_size: 12,
      latency_ms: 150,
      llm_tokens: 42,
    })
  })
})
