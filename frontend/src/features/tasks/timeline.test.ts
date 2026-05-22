import { describe, expect, it } from 'vitest'
import { INITIAL_TIMELINE, applyTaskEvent, sortTaskEvents } from './timeline'
import type { TaskEvent } from './taskTypes'

describe('applyTaskEvent', () => {
  it('starts with exactly four AdaCascade agents', () => {
    expect(Object.keys(INITIAL_TIMELINE)).toEqual(['Planner', 'Profiling', 'Retrieval', 'Matcher'])
  })

  it('marks a retrieval layer step as running then success and records output size', () => {
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
    expect(running.Retrieval.status).toBe('running')
    expect(running.Retrieval.currentStepId).toBe('L1')
    expect(running.Retrieval.steps.find((step) => step.id === 'L1')).toMatchObject({
      status: 'running',
      label: 'Lexical filter',
    })

    const success = applyTaskEvent(running, completed)
    expect(success.Retrieval.currentStepId).toBe('L1')
    expect(success.Retrieval.steps.find((step) => step.id === 'L1')).toMatchObject({
      status: 'success',
      output_size: 80,
      started_at: '2026-04-27T00:00:00Z',
      finished_at: '2026-04-27T00:00:01Z',
    })
    expect(success).not.toHaveProperty('Retrieval:L1')
  })

  it('marks retrieval layer degraded events as degraded with reason and fallback', () => {
    const degraded = applyTaskEvent(INITIAL_TIMELINE, {
      task_id: 'task-1',
      type: 'agent_degraded',
      agent: 'Retrieval',
      layer: 'L2',
      reason: 'qdrant down',
      fallback: 'reuse L1 candidates',
      timestamp: '2026-04-27T00:00:00Z',
    })

    expect(degraded.Retrieval.status).toBe('degraded')
    expect(degraded.Retrieval.currentStepId).toBe('L2')
    expect(degraded.Retrieval.steps.find((step) => step.id === 'L2')).toMatchObject({
      status: 'degraded',
      reason: 'qdrant down',
      fallback: 'reuse L1 candidates',
    })
  })

  it('updates layerless Planner events without creating ad-hoc nodes', () => {
    const updated = applyTaskEvent(INITIAL_TIMELINE, {
      task_id: 'task-1',
      type: 'agent_started',
      agent: 'Planner',
      timestamp: '2026-04-27T00:00:00Z',
    })

    expect(updated.Planner.status).toBe('running')
    expect(updated.Planner.currentStepId).toBe('overview')
    expect(updated.Planner.steps.find((step) => step.id === 'overview')).toMatchObject({
      status: 'running',
    })
    expect(updated).not.toHaveProperty('Planner:undefined')
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

  it('preserves previous step metrics when a later event omits them', () => {
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

    expect(completed.Matcher.steps.find((step) => step.id === 'LLM')).toMatchObject({
      status: 'success',
      input_size: 0,
      output_size: 12,
      latency_ms: 150,
      llm_tokens: 42,
    })
  })

  it('does not reopen an earlier matcher step when a stale start event arrives after completion', () => {
    const afterCompletedDecision = applyTaskEvent(INITIAL_TIMELINE, {
      task_id: 'task-1',
      type: 'agent_completed',
      agent: 'Matcher',
      layer: 'decision',
      output_size: 3,
      timestamp: '2026-04-27T00:00:03Z',
    })

    const withStaleLlmStart = applyTaskEvent(afterCompletedDecision, {
      task_id: 'task-1',
      type: 'agent_started',
      agent: 'Matcher',
      layer: 'LLM',
      input_size: 12,
      timestamp: '2026-04-27T00:00:02Z',
    })

    expect(withStaleLlmStart.Matcher.status).toBe('success')
    expect(withStaleLlmStart.Matcher.currentStepId).toBe('decision')
    const llmStep = withStaleLlmStart.Matcher.steps.find((step) => step.id === 'LLM')
    expect(llmStep).toMatchObject({ status: 'pending' })
    expect(llmStep).not.toHaveProperty('started_at')
    expect(withStaleLlmStart.Matcher.steps.find((step) => step.id === 'decision')).toMatchObject({
      status: 'success',
      finished_at: '2026-04-27T00:00:03Z',
    })
  })

  it('keeps a later agent pending when an out-of-order start event predates the current running agent', () => {
    const plannerRunning = applyTaskEvent(INITIAL_TIMELINE, {
      task_id: 'task-1',
      type: 'agent_started',
      agent: 'Planner',
      timestamp: '2026-04-27T00:00:05Z',
    })

    const withStaleRetrievalStart = applyTaskEvent(plannerRunning, {
      task_id: 'task-1',
      type: 'agent_started',
      agent: 'Retrieval',
      layer: 'L1',
      timestamp: '2026-04-27T00:00:04Z',
    })

    expect(withStaleRetrievalStart.Planner.status).toBe('running')
    expect(withStaleRetrievalStart.Retrieval.status).toBe('pending')
    expect(withStaleRetrievalStart.Retrieval.currentStepId).toBeUndefined()
  })

  it('sorts same-second lifecycle events by pipeline stage before raw timestamp', () => {
    const sorted = sortTaskEvents([
      {
        task_id: 'task-1',
        type: 'agent_started',
        agent: 'Retrieval',
        layer: 'L2',
        timestamp: '2026-04-27T00:00:00.050Z',
      },
      {
        task_id: 'task-1',
        type: 'agent_completed',
        agent: 'Retrieval',
        layer: 'L1',
        timestamp: '2026-04-27T00:00:00.100Z',
      },
      {
        task_id: 'task-1',
        type: 'agent_started',
        agent: 'Retrieval',
        layer: 'L1',
        timestamp: '2026-04-27T00:00:00.000Z',
      },
      {
        task_id: 'task-1',
        type: 'agent_completed',
        agent: 'Retrieval',
        layer: 'L2',
        timestamp: '2026-04-27T00:00:00.150Z',
      },
    ])

    expect(sorted.map((event) => `${event.layer}:${event.type}`)).toEqual([
      'L1:agent_started',
      'L1:agent_completed',
      'L2:agent_started',
      'L2:agent_completed',
    ])
  })

  it('places aggregate matcher completion after all matcher layer events in the same second', () => {
    const sorted = sortTaskEvents([
      {
        task_id: 'task-1',
        type: 'agent_completed',
        agent: 'Matcher',
        timestamp: '2026-04-27T00:00:00.000Z',
      },
      {
        task_id: 'task-1',
        type: 'agent_started',
        agent: 'Matcher',
        layer: 'LLM',
        timestamp: '2026-04-27T00:00:00.000Z',
      },
      {
        task_id: 'task-1',
        type: 'agent_completed',
        agent: 'Matcher',
        layer: 'decision',
        timestamp: '2026-04-27T00:00:00.000Z',
      },
    ])

    expect(sorted.map((event) => `${event.layer ?? 'agent'}:${event.type}`)).toEqual([
      'LLM:agent_started',
      'decision:agent_completed',
      'agent:agent_completed',
    ])
  })
})
