import { fetchEventSource } from '@microsoft/fetch-event-source'
import { API_BASE_URL, buildHeaders, joinUrl } from './client'
import type { TaskEvent } from '../features/tasks/taskTypes'

function isTaskEvent(value: unknown): value is TaskEvent {
  return (
    typeof value === 'object' &&
    value !== null &&
    'task_id' in value &&
    'type' in value &&
    'timestamp' in value
  )
}

export function subscribeTaskEvents(
  tenantId: string,
  taskId: string,
  onEvent: (event: TaskEvent) => void,
  signal: AbortSignal,
): Promise<void> {
  return fetchEventSource(joinUrl(API_BASE_URL, `/tasks/${encodeURIComponent(taskId)}/events`), {
    headers: buildHeaders(tenantId),
    signal,
    onopen(response) {
      if (!response.ok) {
        throw new Error(
          `Task event stream failed with ${response.status} ${response.statusText}`.trim(),
        )
      }

      const contentType = response.headers.get('content-type') ?? ''
      if (!contentType.includes('text/event-stream')) {
        throw new Error(`Task event stream returned unexpected content type: ${contentType || 'unknown'}`)
      }

      return Promise.resolve()
    },
    onmessage(message) {
      if (!message.data) {
        return
      }

      let parsed: unknown
      try {
        parsed = JSON.parse(message.data)
      } catch (error) {
        const messageText = error instanceof Error ? error.message : 'Unknown JSON parse error'
        throw new Error(`Invalid task event payload: ${messageText}`)
      }

      if (!isTaskEvent(parsed)) {
        throw new Error('Invalid task event payload shape')
      }

      onEvent(parsed)
    },
    onerror(error) {
      throw error
    },
  })
}
