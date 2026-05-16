import { apiJson } from './client'
import type { TableSummary } from '../features/tasks/taskTypes'

export type ListTablesResponse = {
  items: TableSummary[]
  total: number
  limit: number
  offset: number
}

export function listTables(tenantId: string, datasetId?: string): Promise<ListTablesResponse> {
  const params = new URLSearchParams({ status: 'READY', limit: '200' })
  if (datasetId) params.set('dataset_id', datasetId)
  return apiJson<ListTablesResponse>(`/tables?${params.toString()}`, tenantId)
}
