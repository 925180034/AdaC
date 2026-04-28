import { apiJson } from './client'
import type { TableSummary } from '../features/tasks/taskTypes'

export type ListTablesResponse = {
  items: TableSummary[]
  total: number
  limit: number
  offset: number
}

export function listTables(tenantId: string): Promise<ListTablesResponse> {
  return apiJson<ListTablesResponse>('/tables?status=READY&limit=200', tenantId)
}
