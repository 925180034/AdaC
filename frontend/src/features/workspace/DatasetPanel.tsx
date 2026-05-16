import { useState, type DragEvent } from 'react'
import type { DatasetSummary, UploadDatasetTablesResponse } from '../../api/datasets'
import type { TableSummary } from '../tasks/taskTypes'
import { getWorkspaceCopy } from './i18n'
import type { Language } from './uiPreferences'

export type DatasetPanelProps = {
  datasets: DatasetSummary[]
  selectedDatasetId: string
  tables: TableSummary[]
  isLoading: boolean
  isMutating: boolean
  uploadSummary: UploadDatasetTablesResponse | null
  error: string | null
  onDatasetChange: (datasetId: string) => void
  onCreateDataset: (payload: { dataset_name: string; description?: string }) => void
  onUploadTables: (files: File[], options: { uploadedBy?: string; tableNamePrefix?: string }) => void
  onRefresh: () => void
  language?: Language
}

function countInProgress(tables: TableSummary[]): number {
  return tables.filter((table) => table.status === 'INGESTED' || table.status === 'PROFILING').length
}

type DroppedFileEntry = {
  isFile: true
  file: (callback: (file: File) => void) => void
}

type DroppedDirectoryEntry = {
  isFile: false
  isDirectory: true
  createReader: () => {
    readEntries: (callback: (entries: DroppedEntry[]) => void) => void
  }
}

type DroppedEntry = DroppedFileEntry | DroppedDirectoryEntry

type DroppedItem = {
  webkitGetAsEntry?: () => DroppedEntry | null
}

function datasetLabel(dataset: DatasetSummary): string {
  return `${dataset.dataset_name} · ${dataset.ready_count}/${dataset.table_count}`
}

function readFileEntry(entry: DroppedFileEntry): Promise<File> {
  return new Promise((resolve) => entry.file(resolve))
}

function readDirectoryEntries(entry: DroppedDirectoryEntry): Promise<DroppedEntry[]> {
  const reader = entry.createReader()
  return new Promise((resolve) => reader.readEntries(resolve))
}

async function readDroppedEntry(entry: DroppedEntry): Promise<File[]> {
  if (entry.isFile) return [await readFileEntry(entry)]

  const entries = await readDirectoryEntries(entry)
  const nestedFiles = await Promise.all(entries.map(readDroppedEntry))
  return nestedFiles.flat()
}

async function readDroppedItems(items: DataTransferItemList): Promise<File[]> {
  const entries = Array.from(items)
    .map((item) => (item as DroppedItem).webkitGetAsEntry?.())
    .filter((entry): entry is DroppedEntry => Boolean(entry))

  const nestedFiles = await Promise.all(entries.map(readDroppedEntry))
  return nestedFiles.flat()
}

export function DatasetPanel({
  datasets,
  selectedDatasetId,
  tables,
  isLoading,
  isMutating,
  uploadSummary,
  error,
  onDatasetChange,
  onCreateDataset,
  onUploadTables,
  onRefresh,
  language = 'en',
}: DatasetPanelProps) {
  const copy = getWorkspaceCopy(language).dataset
  const [datasetName, setDatasetName] = useState('')
  const [description, setDescription] = useState('')
  const [uploadedBy, setUploadedBy] = useState('')
  const [tableNamePrefix, setTableNamePrefix] = useState('')
  const [files, setFiles] = useState<File[]>([])
  const selectedDataset = datasets.find((dataset) => dataset.dataset_id === selectedDatasetId) ?? null
  const recentTables = tables.slice(0, 5)

  const handleCreate = () => {
    const trimmedName = datasetName.trim()
    if (!trimmedName || isMutating) return
    onCreateDataset({ dataset_name: trimmedName, description: description.trim() || undefined })
    setDatasetName('')
    setDescription('')
  }

  const handleUpload = () => {
    if (files.length === 0 || isMutating || !selectedDatasetId) return
    onUploadTables(files, {
      uploadedBy: uploadedBy.trim() || undefined,
      tableNamePrefix: tableNamePrefix.trim() || undefined,
    })
    setFiles([])
  }

  const handleDrop = async (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault()
    if (isMutating || !selectedDatasetId) return

    const droppedFiles =
      event.dataTransfer.items.length > 0
        ? await readDroppedItems(event.dataTransfer.items)
        : Array.from(event.dataTransfer.files)
    setFiles(droppedFiles)
  }

  return (
    <aside className="panel dataset-panel" aria-labelledby="dataset-panel-title">
      <div className="panel__header">
        <div>
          <p className="panel-kicker">{copy.kicker}</p>
          <h2 id="dataset-panel-title">{copy.title}</h2>
        </div>
        <button className="parameter-reset" type="button" onClick={onRefresh} disabled={isLoading || isMutating}>
          {copy.refresh}
        </button>
      </div>

      {error ? (
        <p className="workspace-status workspace-status--error dataset-panel__error" role="alert">
          {error}
        </p>
      ) : null}

      <div className="field-stack">
        <label className="field" htmlFor="dataset-id">
          <span>{copy.selectDataset}</span>
          <select
            id="dataset-id"
            value={selectedDatasetId}
            onChange={(event) => onDatasetChange(event.target.value)}
            disabled={isLoading || isMutating || datasets.length === 0}
          >
            {datasets.length === 0 ? <option value="">{copy.noDatasets}</option> : null}
            {datasets.map((dataset) => (
              <option key={dataset.dataset_id} value={dataset.dataset_id}>
                {datasetLabel(dataset)}
              </option>
            ))}
          </select>
        </label>

        <dl className="control-panel__meta" aria-label={copy.countsLabel}>
          <div>
            <dt>{copy.tables}</dt>
            <dd>{selectedDataset?.table_count ?? 0}</dd>
          </div>
          <div>
            <dt>{copy.ready}</dt>
            <dd>{selectedDataset?.ready_count ?? 0}</dd>
          </div>
          <div>
            <dt>{copy.inProgress}</dt>
            <dd>{countInProgress(tables)}</dd>
          </div>
          <div>
            <dt>{copy.failed}</dt>
            <dd>{selectedDataset?.failed_count ?? 0}</dd>
          </div>
        </dl>

        <section className="dataset-panel__section" aria-labelledby="dataset-create-title">
          <h3 id="dataset-create-title">{copy.createTitle}</h3>
          <label className="field" htmlFor="dataset-name">
            <span>{copy.datasetName}</span>
            <input
              id="dataset-name"
              type="text"
              value={datasetName}
              onChange={(event) => setDatasetName(event.currentTarget.value)}
              disabled={isMutating}
            />
          </label>
          <label className="field" htmlFor="dataset-description">
            <span>{copy.description}</span>
            <input
              id="dataset-description"
              type="text"
              value={description}
              onChange={(event) => setDescription(event.currentTarget.value)}
              disabled={isMutating}
            />
          </label>
          <button className="parameter-reset" type="button" onClick={handleCreate} disabled={!datasetName.trim() || isMutating}>
            {copy.create}
          </button>
        </section>

        <section className="dataset-panel__section" aria-labelledby="dataset-upload-title">
          <h3 id="dataset-upload-title">{copy.uploadTitle}</h3>
          <label className="field" htmlFor="dataset-files">
            <span>{copy.files}</span>
            <input
              id="dataset-files"
              type="file"
              multiple
              accept=".csv,.parquet,.xlsx,.zip"
              onChange={(event) => setFiles(Array.from(event.currentTarget.files ?? []))}
              disabled={isMutating || !selectedDatasetId}
            />
          </label>
          <label className="field" htmlFor="dataset-folder">
            <span>{copy.folder}</span>
            <input
              id="dataset-folder"
              type="file"
              multiple
              // @ts-expect-error Chromium folder picker attribute
              webkitdirectory=""
              onChange={(event) => setFiles(Array.from(event.currentTarget.files ?? []))}
              disabled={isMutating || !selectedDatasetId}
            />
          </label>
          <div
            className="dataset-panel__dropzone"
            aria-label={copy.dropZone}
            onDragOver={(event) => event.preventDefault()}
            onDrop={(event) => void handleDrop(event)}
          >
            {files.length > 0 ? copy.selectedFiles(files.length) : copy.dropZone}
          </div>
          <label className="field" htmlFor="uploaded-by">
            <span>{copy.uploadedBy}</span>
            <input
              id="uploaded-by"
              type="text"
              value={uploadedBy}
              onChange={(event) => setUploadedBy(event.currentTarget.value)}
              disabled={isMutating || !selectedDatasetId}
            />
          </label>
          <label className="field" htmlFor="table-name-prefix">
            <span>{copy.tableNamePrefix}</span>
            <input
              id="table-name-prefix"
              type="text"
              value={tableNamePrefix}
              onChange={(event) => setTableNamePrefix(event.currentTarget.value)}
              disabled={isMutating || !selectedDatasetId}
            />
          </label>
          <button
            className="run-button"
            type="button"
            onClick={handleUpload}
            disabled={files.length === 0 || isMutating || !selectedDatasetId}
          >
            {isMutating ? copy.uploading : copy.upload}
          </button>
        </section>

        {uploadSummary ? (
          <section className="dataset-panel__section" aria-labelledby="dataset-upload-summary-title">
            <h3 id="dataset-upload-summary-title">{copy.uploadSummary}</h3>
            <div className="dataset-panel__summary-grid">
              <span>{copy.accepted(uploadSummary.accepted.length)}</span>
              <span>{copy.rejected(uploadSummary.rejected.length)}</span>
              <span>{copy.skipped(uploadSummary.skipped.length)}</span>
            </div>
            {[...uploadSummary.accepted, ...uploadSummary.rejected, ...uploadSummary.skipped].slice(0, 5).map((item) => (
              <p className="dataset-panel__summary-line" key={`${item.source}-${item.table_id ?? item.reason ?? 'ok'}`}>
                {item.source}: {item.table_name ?? item.reason ?? item.table_id}
              </p>
            ))}
          </section>
        ) : null}

        <section className="dataset-panel__section" aria-labelledby="dataset-recent-title">
          <h3 id="dataset-recent-title">{copy.recentTables}</h3>
          {recentTables.length === 0 ? <p className="control-panel__note">{copy.noTables}</p> : null}
          {recentTables.map((table) => (
            <p className="dataset-panel__table" key={table.table_id}>
              <span>{table.table_name}</span>
              <strong>{table.status}</strong>
            </p>
          ))}
        </section>
      </div>
    </aside>
  )
}
