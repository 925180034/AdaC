import { useEffect, useMemo, useRef, useState } from 'react'
import { StatusBadge } from '../../components/StatusBadge'
import type { TaskEvent } from '../tasks/taskTypes'
import { isKnownAgentId, translateTimeline } from '../tasks/timeline'
import type { TimelineNode, TimelineState, TimelineStep } from '../tasks/timeline'
import { getWorkspaceCopy } from './i18n'
import type { Language } from './uiPreferences'

type AgentTracePanelProps = {
  timeline: TimelineState
  events: TaskEvent[]
  streamError?: string | null
  language?: Language
}

function eventLine(event: TaskEvent, defaultActor: string): string {
  const actor = event.agent ? `${event.agent}${event.layer ? `/${event.layer}` : ''}` : defaultActor
  const message = event.message ?? event.reason ?? event.error ?? event.type.replace(/_/g, ' ')
  return `${new Date(event.timestamp).toLocaleTimeString()} · ${actor} · ${message}`
}

function formatCount(value: number | undefined): string | null {
  if (value === undefined) return null
  return value.toLocaleString()
}

function stepFact(step: TimelineStep, copy: ReturnType<typeof getWorkspaceCopy>['trace']): string | null {
  const input = formatCount(step.input_size)
  const output = formatCount(step.output_size)

  if (input && output) return copy.candidates(input, output)
  if (output) return copy.produced(output)
  if (input) return copy.queued(input)
  return null
}

function completedSteps(node: TimelineNode): number {
  return node.steps.filter((step) => step.status === 'success' || step.status === 'degraded').length
}

function agentPurpose(node: TimelineNode, copy: ReturnType<typeof getWorkspaceCopy>['trace']): string {
  return isKnownAgentId(node.id) ? copy.agents[node.id].purpose : ''
}

function agentFact(node: TimelineNode, copy: ReturnType<typeof getWorkspaceCopy>['trace']): string {
  const done = completedSteps(node)
  if (node.status === 'pending') return copy.waiting
  return copy.stepsComplete(done, node.steps.length)
}

function activeStep(node: TimelineNode): TimelineStep | undefined {
  return node.steps.find((step) => step.id === node.currentStepId)
}

function visibleMessage(node: TimelineNode): string | null {
  const current = activeStep(node)
  return current?.reason ?? current?.message ?? node.reason ?? node.message ?? null
}

function fallbackMessage(node: TimelineNode, copy: ReturnType<typeof getWorkspaceCopy>['trace']): string | null {
  const fallback = activeStep(node)?.fallback
  return fallback ? copy.fallback(fallback) : null
}

function elapsedSeconds(step: TimelineStep, now: number): number | null {
  if (step.latency_ms !== undefined) return Math.max(0, Math.round(step.latency_ms / 1000))
  if (!step.started_at) return null
  const start = Date.parse(step.started_at)
  const end = step.finished_at ? Date.parse(step.finished_at) : now
  if (Number.isNaN(start) || Number.isNaN(end)) return null
  return Math.max(0, Math.round((end - start) / 1000))
}

function hasRunningStep(nodes: TimelineNode[]): boolean {
  return nodes.some((node) => node.steps.some((step) => step.status === 'running'))
}

export function AgentTracePanel({ timeline, events, streamError = null, language = 'en' }: AgentTracePanelProps) {
  const copy = getWorkspaceCopy(language).trace
  const nodes = useMemo(() => Object.values(translateTimeline(timeline, language)), [language, timeline])
  const [now, setNow] = useState(() => Date.now())
  const activeStepRef = useRef<HTMLLIElement | null>(null)
  const activeStepKey = nodes.map((node) => `${node.id}:${node.currentStepId ?? ''}:${node.status}`).join('|')

  useEffect(() => {
    if (!hasRunningStep(nodes)) return undefined
    const timer = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(timer)
  }, [nodes])

  useEffect(() => {
    activeStepRef.current?.scrollIntoView({ block: 'nearest' })
  }, [activeStepKey])

  return (
    <aside className="panel trace-panel" aria-labelledby="trace-title">
      <div className="panel__header">
        <div>
          <p className="panel-kicker">{copy.kicker}</p>
          <h2 id="trace-title">{copy.title}</h2>
        </div>
        <span className="trace-panel__count">{copy.eventCount(events.length)}</span>
      </div>

      <ol className="agent-board" aria-label={copy.pipelineLabel}>
        {nodes.map((node) => {
          const message = visibleMessage(node)
          const fallback = fallbackMessage(node, copy)

          return (
            <li key={node.id}>
              <article className={`agent-card agent-card--${node.status}`} aria-label={node.label}>
                <div className="agent-card__topline">
                  <div>
                    <h3>{node.label}</h3>
                    <p>{agentPurpose(node, copy)}</p>
                  </div>
                  <StatusBadge status={node.status} size="sm" />
                </div>

                <ol className="agent-steps" aria-label={copy.stepsLabel(node.label)}>
                  {node.steps.map((step) => {
                    const isCurrent = step.id === node.currentStepId
                    const fact = stepFact(step, copy)

                    const elapsed = elapsedSeconds(step, now)

                    return (
                      <li
                        className={`agent-step agent-step--${step.status}${isCurrent ? ' agent-step--active' : ''}`}
                        key={step.id}
                        ref={isCurrent ? activeStepRef : undefined}
                      >
                        <div className="agent-step__main">
                          <span className="agent-step__dot" aria-hidden="true" />
                          <span>{step.label}</span>
                        </div>
                        {isCurrent ? <span className="agent-step__current">{copy.currentStep}</span> : null}
                        <p className="agent-step__summary">{step.summary}</p>
                        {elapsed !== null ? <span className="agent-step__fact">{copy.elapsed(elapsed)}</span> : null}
                        {fact ? <span className="agent-step__fact">{fact}</span> : null}
                      </li>
                    )
                  })}
                </ol>

                <div className="agent-facts">
                  <span>{agentFact(node, copy)}</span>
                  {message ? <span>{message}</span> : null}
                  {fallback ? <span>{fallback}</span> : null}
                </div>
              </article>
            </li>
          )
        })}
      </ol>

      <section className="event-stream" aria-labelledby="event-stream-title">
        <div className="section-title-row">
          <h3 id="event-stream-title">{copy.eventsTitle}</h3>
          <span>{copy.eventsKicker}</span>
        </div>
        {streamError ? (
          <p className="event-stream__error" role="status">
            {streamError}
          </p>
        ) : null}
        <div className="event-stream__lines" role="log" aria-live="polite">
          {events.map((event) => (
            <p key={`${event.timestamp}-${event.task_id}-${event.type}-${event.agent ?? 'task'}`}>
              {eventLine(event, copy.defaultActor)}
            </p>
          ))}
        </div>
      </section>
    </aside>
  )
}
