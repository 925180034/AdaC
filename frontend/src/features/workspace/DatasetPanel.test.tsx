import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import type { DatasetSummary } from '../../api/datasets'
import type { TableSummary } from '../tasks/taskTypes'
import { DatasetPanel } from './DatasetPanel'

const datasets: DatasetSummary[] = [
  {
    dataset_id: 'dataset-default',
    dataset_name: 'Default Dataset',
    description: null,
    is_system: false,
    table_count: 1,
    ready_count: 1,
    failed_count: 0,
    created_at: '2026-05-16T00:00:00Z',
    updated_at: '2026-05-16T00:00:00Z',
  },
]

const tables: TableSummary[] = [
  {
    table_id: 'default_table',
    tenant_id: 'default',
    dataset_id: 'dataset-default',
    table_name: 'Default Tenant Table',
    row_count: 10,
    col_count: 3,
    status: 'READY',
  },
]

const baseProps = {
  datasets,
  selectedDatasetId: 'dataset-default',
  tables,
  isLoading: false,
  isMutating: false,
  uploadSummary: null,
  error: null,
  onDatasetChange: vi.fn(),
  onCreateDataset: vi.fn(),
  onUploadTables: vi.fn(),
  onRefresh: vi.fn(),
}

describe('DatasetPanel', () => {
  it('calls onPreviewTable when a recent table button is clicked', async () => {
    const user = userEvent.setup()
    const onPreviewTable = vi.fn()
    render(<DatasetPanel {...baseProps} onPreviewTable={onPreviewTable} />)

    await user.click(screen.getByRole('button', { name: 'Show Dataset tools' }))
    await user.click(screen.getByRole('button', { name: 'Default Tenant Table' }))

    expect(onPreviewTable).toHaveBeenCalledTimes(1)
    expect(onPreviewTable).toHaveBeenCalledWith('default_table')
  })

  it('disables recent table preview buttons when no preview handler is provided', async () => {
    const user = userEvent.setup()
    render(<DatasetPanel {...baseProps} />)

    await user.click(screen.getByRole('button', { name: 'Show Dataset tools' }))

    expect(screen.getByRole('button', { name: 'Default Tenant Table' })).toBeDisabled()
  })
})
