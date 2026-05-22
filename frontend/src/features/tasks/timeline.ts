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
  started_at?: string
  finished_at?: string
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

const terminalStatuses = new Set<TimelineStatus>(['success', 'degraded', 'failed'])
const agentOrder = new Map<AgentId, number>(agentDefinitions.map((agent, index) => [agent.id, index]))

function getEventAgentId(event: TaskEvent): AgentId | null {
  if (!event.agent || !isKnownAgentId(event.agent)) return null
  return event.agent
}

function getEventStepId(node: TimelineNode, event: TaskEvent): string | null {
  const stepId = event.layer ?? 'overview'
  return node.steps.some((step) => step.id === stepId) ? stepId : null
}

function eventTime(event: TaskEvent): number {
  const time = Date.parse(event.timestamp)
  return Number.isNaN(time) ? Number.NEGATIVE_INFINITY : time
}

function stepTime(step: TimelineStep, key: 'started_at' | 'finished_at'): number {
  const timestamp = step[key]
  if (!timestamp) return Number.NEGATIVE_INFINITY
  const time = Date.parse(timestamp)
  return Number.isNaN(time) ? Number.NEGATIVE_INFINITY : time
}

function getTimelineStatus(event: TaskEvent, currentStatus: TimelineStatus): TimelineStatus {
  if (event.type === 'agent_started') return terminalStatuses.has(currentStatus) ? currentStatus : 'running'
  if (event.type === 'agent_degraded') return 'degraded'
  if (event.type === 'agent_failed') return 'failed'
  if (event.type === 'agent_completed') return 'success'
  return currentStatus
}

function getStepStartedAt(event: TaskEvent, step: TimelineStep): string | undefined {
  if (event.type !== 'agent_started') return step.started_at
  if (step.finished_at && eventTime(event) <= stepTime(step, 'finished_at')) return step.started_at
  if (step.started_at && eventTime(event) < stepTime(step, 'started_at')) return step.started_at
  return event.timestamp
}

function getStepFinishedAt(event: TaskEvent, step: TimelineStep): string | undefined {
  const isTerminalEvent = event.type === 'agent_completed' || event.type === 'agent_degraded' || event.type === 'agent_failed'
  if (!isTerminalEvent) return step.finished_at
  if (step.finished_at && eventTime(event) < stepTime(step, 'finished_at')) return step.finished_at
  return event.timestamp
}

function deriveAgentStatus(steps: TimelineStep[]): TimelineStatus {
  if (steps.some((step) => step.status === 'failed')) return 'failed'
  if (steps.some((step) => step.status === 'degraded')) return 'degraded'
  if (steps.some((step) => step.status === 'running')) return 'running'
  if (terminalStatuses.has(steps.at(-1)?.status ?? 'pending')) return 'success'
  if (steps.some((step) => step.status === 'success')) return 'running'
  return 'pending'
}

function getCurrentStepId(steps: TimelineStep[], fallbackStepId: string): string {
  const running = steps.find((step) => step.status === 'running')
  if (running) return running.id

  const latestTerminal = [...steps]
    .sort((left, right) => stepTime(right, 'finished_at') - stepTime(left, 'finished_at'))
    .find((step) => step.status === 'success' || step.status === 'degraded' || step.status === 'failed')
  return latestTerminal?.id ?? fallbackStepId
}

function shouldIgnoreOutOfOrderEvent(state: TimelineState, event: TaskEvent, agentId: AgentId): boolean {
  if (event.type !== 'agent_started') return false

  const currentAgentOrder = agentOrder.get(agentId) ?? Number.MAX_SAFE_INTEGER
  const laterTerminalStepExists = state[agentId].steps.some(
    (timelineStep) => terminalStatuses.has(timelineStep.status) && stepTime(timelineStep, 'finished_at') >= eventTime(event),
  )
  if (laterTerminalStepExists) return true

  return agentDefinitions.some((definition) => {
    const definitionOrder = agentOrder.get(definition.id) ?? Number.MAX_SAFE_INTEGER
    if (definitionOrder >= currentAgentOrder) return false
    return state[definition.id].steps.some(
      (timelineStep) => timelineStep.status === 'running' && stepTime(timelineStep, 'started_at') >= eventTime(event),
    )
  })
}

const eventTypeOrder = new Map<TaskEvent['type'], number>([
  ['task_created', 0],
  ['agent_started', 1],
  ['agent_degraded', 2],
  ['agent_failed', 2],
  ['agent_completed', 3],
  ['task_completed', 4],
  ['heartbeat', 5],
])
const stepOrder = new Map<string, number>([
  ['overview', 0],
  ['L1', 0],
  ['filtering', 0],
  ['L2', 1],
  ['LLM', 1],
  ['L3', 2],
  ['decision', 2],
])

function eventOrder(event: TaskEvent): number {
  return eventTypeOrder.get(event.type) ?? Number.MAX_SAFE_INTEGER
}

function eventAgentOrder(event: TaskEvent): number {
  if (!event.agent || !isKnownAgentId(event.agent)) return event.type === 'task_created' ? -1 : Number.MAX_SAFE_INTEGER
  return agentOrder.get(event.agent) ?? Number.MAX_SAFE_INTEGER
}

function eventStepOrder(event: TaskEvent): number {
  if (!event.layer && (event.agent === 'Retrieval' || event.agent === 'Matcher')) return Number.MAX_SAFE_INTEGER - 1
  return stepOrder.get(event.layer ?? 'overview') ?? Number.MAX_SAFE_INTEGER
}

export function sortTaskEvents(events: TaskEvent[]): TaskEvent[] {
  return [...events].sort((left, right) => {
    const byTime = eventTime(left) - eventTime(right)
    if (byTime !== 0 && Math.abs(byTime) > 1000) return byTime

    const byAgent = eventAgentOrder(left) - eventAgentOrder(right)
    if (byAgent !== 0) return byAgent

    const byStep = eventStepOrder(left) - eventStepOrder(right)
    if (byStep !== 0) return byStep

    const byType = eventOrder(left) - eventOrder(right)
    if (byType !== 0) return byType

    return byTime
  })
}

export function buildTimelineFromEvents(events: TaskEvent[], initialState: TimelineState = INITIAL_TIMELINE): TimelineState {
  return sortTaskEvents(events).reduce(applyTaskEvent, initialState)
}

export function applyTaskEvent(state: TimelineState, event: TaskEvent): TimelineState {
  const agentId = getEventAgentId(event)
  if (!agentId) return state

  const current = state[agentId]
  if (!current) return state

  const stepId = getEventStepId(current, event)
  if (!stepId) return state

  const currentStep = current.steps.find((step) => step.id === stepId)
  if (currentStep && shouldIgnoreOutOfOrderEvent(state, event, agentId)) return state

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
      started_at: getStepStartedAt(event, step),
      finished_at: getStepFinishedAt(event, step),
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
