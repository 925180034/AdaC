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

type AgentId = 'Planner' | 'Profiling' | 'Retrieval' | 'Matcher'

export type AgentDefinition = {
  id: AgentId
  label: string
  steps: Array<[string, string, string]>
}

export const agentDefinitions: AgentDefinition[] = [
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

const timelineTranslations: Record<Language, Record<AgentId, { label: string; steps: Record<string, { label: string; summary: string }> }>> = {
  en: {
    Planner: {
      label: 'Planner',
      steps: { overview: { label: 'Plan routing', summary: 'Chooses discover, match, or integrate execution path.' } },
    },
    Profiling: {
      label: 'Profiling',
      steps: { overview: { label: 'Table profiling', summary: 'Reads table shape, columns, types, and value statistics.' } },
    },
    Retrieval: {
      label: 'Retrieval',
      steps: {
        L1: { label: 'Lexical filter', summary: 'Uses table text and schema keywords to keep plausible candidates.' },
        L2: { label: 'Vector recall', summary: 'Queries embeddings to recover semantically similar tables.' },
        L3: { label: 'LLM rerank', summary: 'Asks the LLM to rerank the strongest candidates.' },
      },
    },
    Matcher: {
      label: 'Matcher',
      steps: {
        filtering: { label: 'Candidate filter', summary: 'Keeps likely column pairs before expensive verification.' },
        LLM: { label: 'LLM verification', summary: 'Checks semantic equivalence for candidate column pairs.' },
        decision: { label: 'One-to-one decision', summary: 'Selects final non-conflicting column mappings.' },
      },
    },
  },
  zh: {
    Planner: {
      label: '规划',
      steps: { overview: { label: '规划路由', summary: '选择发现、匹配或集成执行路径。' } },
    },
    Profiling: {
      label: '画像',
      steps: { overview: { label: '表画像', summary: '读取表形状、列、类型和值统计。' } },
    },
    Retrieval: {
      label: '检索',
      steps: {
        L1: { label: '词法过滤', summary: '使用表文本和模式关键词保留可能候选。' },
        L2: { label: '向量召回', summary: '查询嵌入，找回语义相近的表。' },
        L3: { label: 'LLM 重排', summary: '让 LLM 重排最强候选。' },
      },
    },
    Matcher: {
      label: '匹配',
      steps: {
        filtering: { label: '候选过滤', summary: '在高成本验证前保留可能的列对。' },
        LLM: { label: 'LLM 验证', summary: '检查候选列对的语义等价性。' },
        decision: { label: '一对一决策', summary: '选择最终无冲突的列映射。' },
      },
    },
  },
}

function buildInitialTimeline(language: Language): TimelineState {
  const translations = timelineTranslations[language]

  return Object.fromEntries(
    agentDefinitions.map((agent) => {
      const agentCopy = translations[agent.id]

      return [
        agent.id,
        {
          id: agent.id,
          label: agentCopy.label,
          status: 'pending' as const,
          steps: agent.steps.map(([id, defaultLabel, defaultSummary]) => ({
            id,
            label: agentCopy.steps[id]?.label ?? defaultLabel,
            summary: agentCopy.steps[id]?.summary ?? defaultSummary,
            status: 'pending' as const,
          })),
        },
      ]
    }),
  )
}

export const INITIAL_TIMELINE: TimelineState = buildInitialTimeline('en')

export function translateTimeline(state: TimelineState, language: Language): TimelineState {
  const translations = timelineTranslations[language]

  return Object.fromEntries(
    Object.entries(state).map(([agentId, node]) => {
      const agentCopy = translations[agentId as AgentId]
      if (!agentCopy) return [agentId, node]

      return [
        agentId,
        {
          ...node,
          label: agentCopy.label,
          steps: node.steps.map((step) => ({
            ...step,
            label: agentCopy.steps[step.id]?.label ?? step.label,
            summary: agentCopy.steps[step.id]?.summary ?? step.summary,
          })),
        },
      ]
    }),
  )
}

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
