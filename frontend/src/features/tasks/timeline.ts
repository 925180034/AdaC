import type { TaskEvent } from './taskTypes'

export type TimelineStatus = 'pending' | 'running' | 'success' | 'degraded' | 'failed'

export type TimelineNode = {
  id: string
  label: string
  status: TimelineStatus
  input_size?: number
  output_size?: number
  latency_ms?: number
  llm_tokens?: number
  reason?: string
  message?: string
}

export type TimelineState = Record<string, TimelineNode>

const initialNodes: Array<[string, string]> = [
  ['Planner', 'Planner'],
  ['Profiling', 'Profiling'],
  ['Retrieval:L1', 'Retrieval L1'],
  ['Retrieval:L2', 'Retrieval L2'],
  ['Retrieval:L3', 'Retrieval L3'],
  ['Matcher:filtering', 'Matcher Filtering'],
  ['Matcher:LLM', 'Matcher LLM'],
  ['Matcher:decision', 'Matcher Decision'],
]

export const INITIAL_TIMELINE: TimelineState = Object.fromEntries(
  initialNodes.map(([id, label]) => [id, { id, label, status: 'pending' as const }]),
)

const knownTimelineIds = new Set(Object.keys(INITIAL_TIMELINE))

function getTimelineNodeId(event: TaskEvent): string | null {
  if (!event.agent) return null

  let id: string
  if (event.agent === 'Retrieval') {
    if (!event.layer) return null
    id = `Retrieval:${event.layer}`
  } else if (event.agent === 'Matcher') {
    if (!event.layer) return null
    id = `Matcher:${event.layer}`
  } else {
    id = event.agent
  }

  return knownTimelineIds.has(id) ? id : null
}

function getTimelineStatus(event: TaskEvent, currentStatus: TimelineStatus): TimelineStatus {
  if (event.type === 'agent_started') return 'running'
  if (event.type === 'agent_degraded') return 'degraded'
  if (event.type === 'agent_failed') return 'failed'
  if (event.type === 'agent_completed') return 'success'
  return currentStatus
}

export function applyTaskEvent(state: TimelineState, event: TaskEvent): TimelineState {
  const id = getTimelineNodeId(event)
  if (!id) return state

  const current = state[id]
  if (!current) return state

  return {
    ...state,
    [id]: {
      ...current,
      status: getTimelineStatus(event, current.status),
      input_size: event.input_size ?? current.input_size,
      output_size: event.output_size ?? current.output_size,
      latency_ms: event.latency_ms ?? current.latency_ms,
      llm_tokens: event.llm_tokens ?? current.llm_tokens,
      reason: event.reason ?? current.reason,
      message: event.message ?? current.message,
    },
  }
}
