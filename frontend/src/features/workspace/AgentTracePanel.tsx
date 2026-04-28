import { StatusBadge } from '../../components/StatusBadge'
import type { TaskEvent } from '../tasks/taskTypes'
import type { TimelineState } from '../tasks/timeline'

type AgentTracePanelProps = {
  timeline: TimelineState
  events: TaskEvent[]
  streamError?: string | null
}

function formatMetric(value: number | undefined, suffix = ''): string {
  if (value === undefined) return '—'
  return `${value.toLocaleString()}${suffix}`
}

function eventLine(event: TaskEvent): string {
  const actor = event.agent ? `${event.agent}${event.layer ? `/${event.layer}` : ''}` : 'Task'
  const message = event.message ?? event.reason ?? event.error ?? event.type.replace(/_/g, ' ')
  return `${new Date(event.timestamp).toLocaleTimeString()} · ${actor} · ${message}`
}

export function AgentTracePanel({ timeline, events, streamError = null }: AgentTracePanelProps) {
  const nodes = Object.values(timeline)

  return (
    <aside className="panel trace-panel" aria-labelledby="trace-title">
      <div className="panel__header">
        <div>
          <p className="panel-kicker">Agent telemetry</p>
          <h2 id="trace-title">Agent Trace</h2>
        </div>
        <span className="trace-panel__count">{events.length} events</span>
      </div>

      <ol className="timeline-list" aria-label="Agent timeline statuses">
        {nodes.map((node) => (
          <li className={`timeline-node timeline-node--${node.status}`} key={node.id}>
            <div className="timeline-node__rail" aria-hidden="true" />
            <div className="timeline-node__content">
              <div className="timeline-node__topline">
                <h3>{node.label}</h3>
                <StatusBadge status={node.status} size="sm" />
              </div>
              {node.message || node.reason ? <p>{node.message ?? node.reason}</p> : null}
              <dl className="timeline-node__metrics">
                <div>
                  <dt>In</dt>
                  <dd>{formatMetric(node.input_size)}</dd>
                </div>
                <div>
                  <dt>Out</dt>
                  <dd>{formatMetric(node.output_size)}</dd>
                </div>
                <div>
                  <dt>Latency</dt>
                  <dd>{formatMetric(node.latency_ms, 'ms')}</dd>
                </div>
                <div>
                  <dt>Tokens</dt>
                  <dd>{formatMetric(node.llm_tokens)}</dd>
                </div>
              </dl>
            </div>
          </li>
        ))}
      </ol>

      <section className="event-stream" aria-labelledby="event-stream-title">
        <div className="section-title-row">
          <h3 id="event-stream-title">Event stream</h3>
          <span>sample</span>
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
