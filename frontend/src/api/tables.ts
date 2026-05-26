import { apiJson } from './client'
import type { TableSummary } from '../features/tasks/taskTypes'

type PreviewCellValue = string | number | boolean | null | PreviewCellValue[] | { [key: string]: PreviewCellValue }

export type ListTablesResponse = {
  items: TableSummary[]
  total: number
  limit: number
  offset: number
}

export type TablePreviewResponse = {
  table: TableSummary
  columns: string[]
  sample_rows: Record<string, PreviewCellValue>[]
  sample_limit: number
}

export function listTables(tenantId: string, datasetId?: string): Promise<ListTablesResponse> {
  const params = new URLSearchParams({ status: 'READY', limit: '200' })
  if (datasetId) params.set('dataset_id', datasetId)
  return apiJson<ListTablesResponse>(`/tables?${params.toString()}`, tenantId)
}

export function getTablePreview(
  tenantId: string,
  tableId: string,
  datasetId?: string,
): Promise<TablePreviewResponse> {
  const params = new URLSearchParams({ limit: '20' })
  if (datasetId) params.set('dataset_id', datasetId)
  return apiJson<TablePreviewResponse>(`/tables/${encodeURIComponent(tableId)}/preview?${params.toString()}`, tenantId)
}
