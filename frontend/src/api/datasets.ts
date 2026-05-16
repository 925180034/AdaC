import { apiJson, apiMultipart } from './client'

export type DatasetSummary = {
  dataset_id: string
  dataset_name: string
  description: string | null
  is_system: boolean
  table_count: number
  ready_count: number
  failed_count: number
  created_at: string
  updated_at: string
}

export type ListDatasetsResponse = {
  items: DatasetSummary[]
}

export type CreateDatasetPayload = {
  dataset_name: string
  description?: string
  created_by?: string
}

export type UploadSummaryItem = {
  source: string
  table_id?: string
  table_name?: string
  reason?: string
}

export type UploadDatasetTablesResponse = {
  dataset_id: string
  accepted: UploadSummaryItem[]
  rejected: UploadSummaryItem[]
  skipped: UploadSummaryItem[]
}

export type UploadDatasetTablesOptions = {
  uploadedBy?: string
  tableNamePrefix?: string
}

export function listDatasets(tenantId: string): Promise<ListDatasetsResponse> {
  return apiJson<ListDatasetsResponse>('/datasets', tenantId)
}

export function createDataset(tenantId: string, payload: CreateDatasetPayload): Promise<DatasetSummary> {
  return apiJson<DatasetSummary>('/datasets', tenantId, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function uploadDatasetTables(
  tenantId: string,
  datasetId: string,
  files: File[],
  options: UploadDatasetTablesOptions = {},
): Promise<UploadDatasetTablesResponse> {
  const body = new FormData()
  for (const file of files) {
    body.append('files', file)
  }
  if (options.uploadedBy) body.append('uploaded_by', options.uploadedBy)
  if (options.tableNamePrefix) body.append('table_name_prefix', options.tableNamePrefix)

  return apiMultipart<UploadDatasetTablesResponse>(`/datasets/${encodeURIComponent(datasetId)}/tables`, tenantId, {
    method: 'POST',
    body,
  })
}
