import { apiJson } from './client'
import type { TaskDetail } from '../features/tasks/taskTypes'

export type StartTaskResponse = {
  task_id: string
  status: 'RUNNING'
  state: Record<string, unknown>
}

export function startDiscover(tenantId: string, queryTableId: string): Promise<StartTaskResponse> {
  return apiJson<StartTaskResponse>('/discover', tenantId, {
    method: 'POST',
    body: JSON.stringify({ query_table_id: queryTableId }),
  })
}

export function startIntegrate(tenantId: string, queryTableId: string): Promise<StartTaskResponse> {
  return apiJson<StartTaskResponse>('/integrate', tenantId, {
    method: 'POST',
    body: JSON.stringify({ query_table_id: queryTableId }),
  })
}

export function startMatch(
  tenantId: string,
  sourceTableId: string,
  targetTableId: string,
): Promise<StartTaskResponse> {
  return apiJson<StartTaskResponse>('/match', tenantId, {
    method: 'POST',
    body: JSON.stringify({ source_table_id: sourceTableId, target_table_id: targetTableId }),
  })
}

export function getTask(tenantId: string, taskId: string): Promise<TaskDetail> {
  return apiJson<TaskDetail>(`/tasks/${encodeURIComponent(taskId)}`, tenantId)
}
