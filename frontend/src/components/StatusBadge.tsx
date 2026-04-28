import type { TimelineStatus } from '../features/tasks/timeline'
import type { TaskStatus } from '../features/tasks/taskTypes'

type StatusTone = 'pending' | 'running' | 'success' | 'degraded' | 'failed' | 'ready'

type StatusBadgeProps = {
  status: TimelineStatus | TaskStatus | string
  label?: string
  size?: 'sm' | 'md'
}

function normalizeStatus(status: string): StatusTone {
  const normalized = status.toLowerCase()
  if (normalized === 'ready') return 'ready'
  if (normalized === 'success' || normalized === 'completed') return 'success'
  if (normalized === 'running' || normalized === 'pending') return normalized
  if (normalized === 'degraded') return 'degraded'
  if (normalized === 'failed' || normalized === 'error') return 'failed'
  return 'pending'
}

export function StatusBadge({ status, label, size = 'md' }: StatusBadgeProps) {
  const tone = normalizeStatus(status)
  const displayLabel = label ?? status.replace(/_/g, ' ')

  return (
    <span className={`status-badge status-badge--${tone} status-badge--${size}`}>
      <span className="status-badge__dot" aria-hidden="true" />
      <span className="status-badge__text">{displayLabel}</span>
    </span>
  )
}
