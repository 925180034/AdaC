import type { TaskEvent } from './taskTypes'

export type TimelineStatus = 'pending' | 'running' | 'success' | 'degraded' | 'failed'

export type TimelineStep = {
  id: string
  label: string
  summary: string
  status: TimelineStatus
  input_size?: number
  output_size?: number
  latency_ms?: number
  llm_tokens?: number
  reason?: string
  message?: string
  fallback?: string
}

export type TimelineNode = {
  id: string
  label: string
  status: TimelineStatus
  steps: TimelineStep[]
  currentStepId?: string
  reason?: string
  message?: string
}

export type TimelineState = Record<string, TimelineNode>

type AgentId = 'Planner' | 'Profiling' | 'Retrieval' | 'Matcher'

type AgentDefinition = {
  id: AgentId
  label: string
  steps: Array<[string, string, string]>
}

const agentDefinitions: AgentDefinition[] = [
  {
    id: 'Planner',
    label: 'Planner',
    steps: [['overview', 'Plan routing', 'Chooses discover, match, or integrate execution path.']],
  },
  {
    id: 'Profiling',
    label: 'Profiling',
    steps: [['overview', 'Table profiling', 'Reads table shape, columns, types, and value statistics.']],
  },
  {
    id: 'Retrieval',
    label: 'Retrieval',
    steps: [
      ['L1', 'Lexical filter', 'Uses table text and schema keywords to keep plausible candidates.'],
      ['L2', 'Vector recall', 'Queries embeddings to recover semantically similar tables.'],
      ['L3', 'LLM rerank', 'Asks the LLM to rerank the strongest candidates.'],
    ],
  },
  {
    id: 'Matcher',
    label: 'Matcher',
    steps: [
      ['filtering', 'Candidate filter', 'Keeps likely column pairs before expensive verification.'],
      ['LLM', 'LLM verification', 'Checks semantic equivalence for candidate column pairs.'],
      ['decision', 'One-to-one decision', 'Selects final non-conflicting column mappings.'],
    ],
  },
]

export const INITIAL_TIMELINE: TimelineState = Object.fromEntries(
  agentDefinitions.map((agent) => [
    agent.id,
    {
      id: agent.id,
      label: agent.label,
      status: 'pending' as const,
      steps: agent.steps.map(([id, label, summary]) => ({ id, label, summary, status: 'pending' as const })),
    },
  ]),
)

const knownAgentIds = new Set(Object.keys(INITIAL_TIMELINE))

function getEventAgentId(event: TaskEvent): AgentId | null {
  if (!event.agent || !knownAgentIds.has(event.agent)) return null
  return event.agent
}

function getEventStepId(node: TimelineNode, event: TaskEvent): string | null {
  const stepId = event.layer ?? 'overview'
  return node.steps.some((step) => step.id === stepId) ? stepId : null
}

function getTimelineStatus(event: TaskEvent, currentStatus: TimelineStatus): TimelineStatus {
  if (event.type === 'agent_started') return 'running'
  if (event.type === 'agent_degraded') return 'degraded'
  if (event.type === 'agent_failed') return 'failed'
  if (event.type === 'agent_completed') return 'success'
  return currentStatus
}

function deriveAgentStatus(steps: TimelineStep[]): TimelineStatus {
  if (steps.some((step) => step.status === 'failed')) return 'failed'
  if (steps.some((step) => step.status === 'degraded')) return 'degraded'
  if (steps.some((step) => step.status === 'running')) return 'running'
  if (steps.some((step) => step.status === 'success')) return 'success'
  return 'pending'
}

function getCurrentStepId(steps: TimelineStep[], fallbackStepId: string): string {
  const running = steps.find((step) => step.status === 'running')
  if (running) return running.id

  const latestTerminal = [...steps]
    .reverse()
    .find((step) => step.status === 'success' || step.status === 'degraded' || step.status === 'failed')
  return latestTerminal?.id ?? fallbackStepId
}

export function applyTaskEvent(state: TimelineState, event: TaskEvent): TimelineState {
  const agentId = getEventAgentId(event)
  if (!agentId) return state

  const current = state[agentId]
  if (!current) return state

  const stepId = getEventStepId(current, event)
  if (!stepId) return state

  const steps = current.steps.map((step) => {
    if (step.id !== stepId) return step

    return {
      ...step,
      status: getTimelineStatus(event, step.status),
      input_size: event.input_size ?? step.input_size,
      output_size: event.output_size ?? step.output_size,
      latency_ms: event.latency_ms ?? step.latency_ms,
      llm_tokens: event.llm_tokens ?? step.llm_tokens,
      reason: event.reason ?? step.reason,
      message: event.message ?? step.message,
      fallback: event.fallback ?? step.fallback,
    }
  })
  const status = deriveAgentStatus(steps)
  const currentStepId = getCurrentStepId(steps, stepId)
  const updatedStep = steps.find((step) => step.id === stepId)

  return {
    ...state,
    [agentId]: {
      ...current,
      status,
      steps,
      currentStepId,
      reason: updatedStep?.reason ?? current.reason,
      message: updatedStep?.message ?? current.message,
    },
  }
}
