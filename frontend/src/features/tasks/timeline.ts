import { getWorkspaceCopy } from '../workspace/i18n'
import type { Language } from '../workspace/uiPreferences'
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

export type AgentId = 'Planner' | 'Profiling' | 'Retrieval' | 'Matcher'

export type AgentStepIdMap = {
  Planner: 'overview'
  Profiling: 'overview'
  Retrieval: 'L1' | 'L2' | 'L3'
  Matcher: 'filtering' | 'LLM' | 'decision'
}

export type KnownStepId = AgentStepIdMap[AgentId]

export type TimelineStepCopy = {
  label: string
  summary: string
}

type AgentTimelineCopy<Agent extends AgentId> = {
  label: string
  purpose: string
  steps: Record<AgentStepIdMap[Agent], TimelineStepCopy> &
    Partial<Record<Exclude<KnownStepId, AgentStepIdMap[Agent]>, TimelineStepCopy>>
}

export type TimelineCopy = {
  [Agent in AgentId]: AgentTimelineCopy<Agent>
}

export type AgentDefinition = {
  [Agent in AgentId]: {
    id: Agent
    steps: AgentStepIdMap[Agent][]
  }
}[AgentId]

export const agentDefinitions = [
  { id: 'Planner', steps: ['overview'] },
  { id: 'Profiling', steps: ['overview'] },
  { id: 'Retrieval', steps: ['L1', 'L2', 'L3'] },
  { id: 'Matcher', steps: ['filtering', 'LLM', 'decision'] },
] satisfies AgentDefinition[]

const knownAgentIds = new Set<AgentId>(agentDefinitions.map((agent) => agent.id))

export function isKnownAgentId(agentId: string): agentId is AgentId {
  return knownAgentIds.has(agentId as AgentId)
}

function buildInitialTimeline(language: Language): TimelineState {
  const translations = getWorkspaceCopy(language).trace.agents

  return Object.fromEntries(
    agentDefinitions.map((agent) => {
      const agentCopy = translations[agent.id]

      return [
        agent.id,
        {
          id: agent.id,
          label: agentCopy.label,
          status: 'pending' as const,
          steps: agent.steps.map((id) => {
            const stepCopy = agentCopy.steps[id]
            if (!stepCopy) {
              throw new Error(`Missing timeline copy for ${agent.id}/${id}`)
            }

            return {
              id,
              label: stepCopy.label,
              summary: stepCopy.summary,
              status: 'pending' as const,
            }
          }),
        },
      ]
    }),
  )
}

export const INITIAL_TIMELINE: TimelineState = buildInitialTimeline('en')

export function translateTimeline(state: TimelineState, language: Language): TimelineState {
  const translations = getWorkspaceCopy(language).trace.agents

  return Object.fromEntries(
    Object.entries(state).map(([agentId, node]) => {
      if (!isKnownAgentId(agentId)) return [agentId, node]
      const agentCopy = translations[agentId]

      return [
        agentId,
        {
          ...node,
          label: agentCopy.label,
          steps: node.steps.map((step) => {
            const stepCopy = agentCopy.steps[step.id as AgentStepIdMap[typeof agentId]]

            return {
              ...step,
              label: stepCopy?.label ?? step.label,
              summary: stepCopy?.summary ?? step.summary,
            }
          }),
        },
      ]
    }),
  )
}

function getEventAgentId(event: TaskEvent): AgentId | null {
  if (!event.agent || !isKnownAgentId(event.agent)) return null
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
