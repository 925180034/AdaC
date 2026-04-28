import { beforeEach, describe, expect, it } from 'vitest'
import { INITIAL_TIMELINE } from './timeline'
import type { TaskEvent } from './taskTypes'
import { useTaskStore } from './taskStore'

function resetStore(): void {
  useTaskStore.setState({
    currentTaskId: null,
    events: [],
    timeline: INITIAL_TIMELINE,
  })
}

describe('useTaskStore', () => {
  beforeEach(() => {
    resetStore()
  })

  it('stores the current task id', () => {
    useTaskStore.getState().setCurrentTaskId('task-123')

    expect(useTaskStore.getState().currentTaskId).toBe('task-123')
  })

  it('appends task events in arrival order', () => {
    const first: TaskEvent = {
      task_id: 'task-123',
      type: 'task_created',
      timestamp: '2026-04-28T00:00:00Z',
    }
    const second: TaskEvent = {
      task_id: 'task-123',
      type: 'heartbeat',
      message: 'still running',
      timestamp: '2026-04-28T00:00:01Z',
    }

    useTaskStore.getState().appendEvent(first)
    useTaskStore.getState().appendEvent(second)

    expect(useTaskStore.getState().events).toEqual([first, second])
  })

  it('ignores stale events for a different current task', () => {
    const currentEvent: TaskEvent = {
      task_id: 'task-current',
      type: 'task_created',
      timestamp: '2026-04-28T00:00:00Z',
    }
    const staleEvent: TaskEvent = {
      task_id: 'task-stale',
      type: 'agent_started',
      agent: 'Planner',
      message: 'stale planning started',
      timestamp: '2026-04-28T00:00:01Z',
    }

    useTaskStore.getState().setCurrentTaskId('task-current')
    useTaskStore.getState().appendEvent(currentEvent)
    useTaskStore.getState().appendEvent(staleEvent)

    expect(useTaskStore.getState().events).toEqual([currentEvent])
    expect(useTaskStore.getState().timeline).toBe(INITIAL_TIMELINE)
  })

  it('preserves current task events after ignoring stale events', () => {
    const staleEvent: TaskEvent = {
      task_id: 'task-stale',
      type: 'agent_started',
      agent: 'Planner',
      message: 'stale planning started',
      timestamp: '2026-04-28T00:00:00Z',
    }
    const currentEvent: TaskEvent = {
      task_id: 'task-current',
      type: 'agent_started',
      agent: 'Planner',
      message: 'planning started',
      timestamp: '2026-04-28T00:00:01Z',
    }

    useTaskStore.getState().setCurrentTaskId('task-current')
    useTaskStore.getState().appendEvent(staleEvent)
    useTaskStore.getState().appendEvent(currentEvent)

    expect(useTaskStore.getState().events).toEqual([currentEvent])
    expect(useTaskStore.getState().timeline.Planner).toMatchObject({
      status: 'running',
      message: 'planning started',
    })
  })

  it('updates the timeline when appending agent events and resets live state', () => {
    const event: TaskEvent = {
      task_id: 'task-123',
      type: 'agent_started',
      agent: 'Planner',
      message: 'planning started',
      timestamp: '2026-04-28T00:00:00Z',
    }

    useTaskStore.getState().appendEvent(event)

    expect(useTaskStore.getState().timeline.Planner).toMatchObject({
      status: 'running',
      message: 'planning started',
    })

    useTaskStore.getState().resetLiveState()

    expect(useTaskStore.getState().events).toEqual([])
    expect(useTaskStore.getState().timeline).toBe(INITIAL_TIMELINE)
  })
})
