import { render, screen, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { applyTaskEvent, INITIAL_TIMELINE } from '../tasks/timeline'
import type { TaskEvent } from '../tasks/taskTypes'
import { AgentTracePanel } from './AgentTracePanel'

const events: TaskEvent[] = [
  {
    task_id: 'task-1',
    type: 'agent_started',
    agent: 'Retrieval',
    layer: 'L2',
    input_size: 80,
    timestamp: '2026-04-28T00:00:00Z',
  },
  {
    task_id: 'task-1',
    type: 'agent_degraded',
    agent: 'Retrieval',
    layer: 'L2',
    output_size: 40,
    reason: 'Qdrant unavailable',
    fallback: 'reuse lexical candidates',
    timestamp: '2026-04-28T00:00:01Z',
  },
  {
    task_id: 'task-1',
    type: 'agent_completed',
    agent: 'Matcher',
    layer: 'decision',
    output_size: 3,
    timestamp: '2026-04-28T00:00:02Z',
  },
]

function timelineFromEvents() {
  return events.reduce(applyTaskEvent, INITIAL_TIMELINE)
}

describe('AgentTracePanel', () => {
  beforeEach(() => {
    Element.prototype.scrollIntoView = vi.fn()
    vi.useRealTimers()
  })

  it('renders exactly four AdaCascade agent cards with nested steps', () => {
    render(<AgentTracePanel timeline={timelineFromEvents()} events={events} />)

    const cards = screen.getAllByRole('article')
    expect(cards).toHaveLength(4)
    expect(cards.map((card) => within(card).getByRole('heading', { level: 3 }).textContent)).toEqual([
      'Planner',
      'Profiling',
      'Retrieval',
      'Matcher',
    ])

    const retrieval = screen.getByRole('article', { name: /Retrieval/ })
    expect(within(retrieval).getByText('Lexical filter')).toBeInTheDocument()
    expect(within(retrieval).getByText('Vector recall')).toBeInTheDocument()
    expect(within(retrieval).getByText('LLM rerank')).toBeInTheDocument()
    expect(within(retrieval).getByText('Uses table text and schema keywords to keep plausible candidates.')).toBeInTheDocument()
    expect(within(retrieval).getByText('Queries embeddings to recover semantically similar tables.')).toBeInTheDocument()
    expect(within(retrieval).getByText('Asks the LLM to rerank the strongest candidates.')).toBeInTheDocument()
    expect(screen.queryByRole('article', { name: /Retrieval L1/ })).not.toBeInTheDocument()
  })

  it('renders academically accurate Chinese agent purpose and step summaries when requested', () => {
    render(<AgentTracePanel timeline={timelineFromEvents()} events={events} language="zh" />)

    expect(screen.getByRole('article', { name: /特征分析智能体/ })).toBeInTheDocument()
    expect(screen.queryByText('画像')).not.toBeInTheDocument()
    expect(screen.getByText('表特征分析')).toBeInTheDocument()

    const retrieval = screen.getByRole('article', { name: /检索智能体/ })
    expect(within(retrieval).getByText('通过三层级联过滤（TLCF）缩小数据湖候选表范围。')).toBeInTheDocument()
    expect(within(retrieval).getByText('向量召回')).toBeInTheDocument()
    expect(within(retrieval).getByText('基于表嵌入召回语义相似候选表。')).toBeInTheDocument()
    expect(within(retrieval).getByText('LLM 复核')).toBeInTheDocument()
    expect(within(retrieval).getByText('当前步骤')).toBeInTheDocument()
    expect(within(retrieval).getByText('80 → 40 个候选')).toBeInTheDocument()
    expect(within(retrieval).getByText('降级：reuse lexical candidates')).toBeInTheDocument()
  })

  it('highlights a running current step, shows elapsed time, and scrolls it into view', () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-04-28T00:00:05Z'))
    const runningEvents: TaskEvent[] = [
      {
        task_id: 'task-1',
        type: 'agent_started',
        agent: 'Retrieval',
        layer: 'L2',
        input_size: 80,
        timestamp: '2026-04-28T00:00:00Z',
      },
    ]
    const runningTimeline = runningEvents.reduce(applyTaskEvent, INITIAL_TIMELINE)
    render(<AgentTracePanel timeline={runningTimeline} events={runningEvents} />)

    const retrieval = screen.getByRole('article', { name: /Retrieval/ })
    expect(within(retrieval).getByText('Current step')).toBeInTheDocument()
    expect(within(retrieval).getByText('5s elapsed')).toBeInTheDocument()
    expect(within(retrieval).getByText('80 queued')).toBeInTheDocument()
    expect(Element.prototype.scrollIntoView).toHaveBeenCalled()
  })

  it('does not render token or latency telemetry as primary agent facts', () => {
    render(<AgentTracePanel timeline={timelineFromEvents()} events={events} />)

    expect(screen.queryByText('Tokens')).not.toBeInTheDocument()
    expect(screen.queryByText('Latency')).not.toBeInTheDocument()
  })
})
