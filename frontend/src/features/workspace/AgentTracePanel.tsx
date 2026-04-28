import { StatusBadge } from '../../components/StatusBadge'
import type { TaskEvent } from '../tasks/taskTypes'
import type { TimelineNode, TimelineState, TimelineStep } from '../tasks/timeline'

type AgentTracePanelProps = {
  timeline: TimelineState
  events: TaskEvent[]
  streamError?: string | null
}

const agentPurpose: Record<string, string> = {
  Planner: 'Builds the task plan and mode routing.',
  Profiling: 'Extracts table and column metadata.',
  Retrieval: 'Narrows the lake with TLCF cascade.',
  Matcher: 'Verifies column alignments and final mappings.',
}

function eventLine(event: TaskEvent): string {
  const actor = event.agent ? `${event.agent}${event.layer ? `/${event.layer}` : ''}` : 'Task'
  const message = event.message ?? event.reason ?? event.error ?? event.type.replace(/_/g, ' ')
  return `${new Date(event.timestamp).toLocaleTimeString()} · ${actor} · ${message}`
}

function formatCount(value: number | undefined): string | null {
  if (value === undefined) return null
  return value.toLocaleString()
}

function stepFact(step: TimelineStep): string | null {
  const input = formatCount(step.input_size)
  const output = formatCount(step.output_size)

  if (input && output) return `${input} → ${output} candidates`
  if (output) return `${output} produced`
  if (input) return `${input} queued`
  return null
}

function completedSteps(node: TimelineNode): number {
  return node.steps.filter((step) => step.status === 'success' || step.status === 'degraded').length
}

function agentFact(node: TimelineNode): string {
  const done = completedSteps(node)
  if (node.status === 'pending') return 'Waiting for task events'
  if (done === node.steps.length) return `${done}/${node.steps.length} steps complete`
  return `${done}/${node.steps.length} steps complete`
}

function activeStep(node: TimelineNode): TimelineStep | undefined {
  return node.steps.find((step) => step.id === node.currentStepId)
}

function visibleMessage(node: TimelineNode): string | null {
  const current = activeStep(node)
  return current?.reason ?? current?.message ?? node.reason ?? node.message ?? null
}

function fallbackMessage(node: TimelineNode): string | null {
  const fallback = activeStep(node)?.fallback
  return fallback ? `Fallback: ${fallback}` : null
}

export function AgentTracePanel({ timeline, events, streamError = null }: AgentTracePanelProps) {
  const nodes = Object.values(timeline)

  return (
    <aside className="panel trace-panel" aria-labelledby="trace-title">
      <div className="panel__header">
        <div>
          <p className="panel-kicker">Agent pipeline</p>
          <h2 id="trace-title">Four-agent execution</h2>
        </div>
        <span className="trace-panel__count">{events.length} events</span>
      </div>

      <ol className="agent-board" aria-label="AdaCascade agent pipeline">
        {nodes.map((node) => {
          const message = visibleMessage(node)
          const fallback = fallbackMessage(node)

          return (
            <li key={node.id}>
              <article className={`agent-card agent-card--${node.status}`} aria-label={node.label}>
                <div className="agent-card__topline">
                  <div>
                    <h3>{node.label}</h3>
                    <p>{agentPurpose[node.id]}</p>
                  </div>
                  <StatusBadge status={node.status} size="sm" />
                </div>

                <ol className="agent-steps" aria-label={`${node.label} steps`}>
                  {node.steps.map((step) => {
                    const isCurrent = step.id === node.currentStepId
                    const fact = stepFact(step)

                    return (
                      <li
                        className={`agent-step agent-step--${step.status}${isCurrent ? ' agent-step--active' : ''}`}
                        key={step.id}
                      >
                        <div className="agent-step__main">
                          <span className="agent-step__dot" aria-hidden="true" />
                          <span>{step.label}</span>
                        </div>
                        {isCurrent ? <span className="agent-step__current">Current step</span> : null}
                        <p className="agent-step__summary">{step.summary}</p>
                        {fact ? <span className="agent-step__fact">{fact}</span> : null}
                      </li>
                    )
                  })}
                </ol>

                <div className="agent-facts">
                  <span>{agentFact(node)}</span>
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
          <h3 id="event-stream-title">Recent events</h3>
          <span>supporting log</span>
        </div>
        {streamError ? (
          <p className="event-stream__error" role="status">
            {streamError}
          </p>
        ) : null}
        <div className="event-stream__lines" role="log" aria-live="polite">
          {events.map((event) => (
            <p key={`${event.timestamp}-${event.task_id}-${event.type}-${event.agent ?? 'task'}`}>
              {eventLine(event)}
            </p>
          ))}
        </div>
      </section>
    </aside>
  )
}
