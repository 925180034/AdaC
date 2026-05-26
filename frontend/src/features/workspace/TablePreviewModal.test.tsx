import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import type { TablePreviewResponse } from '../../api/tables'
import { TablePreviewModal } from './TablePreviewModal'

const preview: TablePreviewResponse = {
  table: {
    table_id: 'table-1',
    tenant_id: 'demo',
    dataset_id: 'dataset-alpha',
    table_name: 'research_projects',
    row_count: 125,
    col_count: 4,
    status: 'READY',
  },
  columns: ['project', 'budget', 'active', 'tags', 'metadata'],
  sample_rows: [
    { project: 'Apollo', budget: 1200, active: true, tags: ['grant', 'public'], metadata: { owner: 'lab' } },
    { project: null, budget: 800, active: false, tags: [], metadata: null },
  ],
  sample_limit: 20,
}

describe('TablePreviewModal', () => {
  it('renders metadata, columns, sample rows, null display, and array cells', () => {
    render(<TablePreviewModal preview={preview} isLoading={false} error={null} onClose={() => undefined} />)

    expect(screen.getByRole('dialog', { name: 'Table preview' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'research_projects' })).toBeInTheDocument()
    expect(screen.getByText('125 rows')).toBeInTheDocument()
    expect(screen.getByText('4 columns')).toBeInTheDocument()
    expect(screen.getByText('READY')).toBeInTheDocument()
    expect(screen.getByText('dataset-alpha')).toBeInTheDocument()

    const table = screen.getByRole('table', { name: 'Sample rows' })
    expect(within(table).getByRole('columnheader', { name: 'project' })).toBeInTheDocument()
    expect(within(table).getByRole('columnheader', { name: 'tags' })).toBeInTheDocument()
    expect(within(table).getByRole('columnheader', { name: 'metadata' })).toBeInTheDocument()
    expect(within(table).getByText('Apollo')).toBeInTheDocument()
    expect(within(table).getByText('grant, public')).toHaveAttribute('title', 'grant, public')
    expect(within(table).getByText('{"owner":"lab"}')).toHaveAttribute('title', '{"owner":"lab"}')
    expect(within(table).getAllByText('—')).toHaveLength(2)
    expect(screen.queryByText('Drag or wheel ↔ ↕')).not.toBeInTheDocument()
  })

  it('focuses the close button, traps tab focus, and closes from button or Escape', async () => {
    const user = userEvent.setup()
    const onClose = vi.fn()
    render(
      <>
        <button type="button">Background action</button>
        <TablePreviewModal preview={preview} isLoading={false} error={null} onClose={onClose} />
      </>,
    )

    const closeButton = screen.getByRole('button', { name: 'Close preview' })
    expect(closeButton).toHaveFocus()

    await user.tab()
    expect(closeButton).toHaveFocus()

    await user.keyboard('{Escape}')
    await user.click(closeButton)

    expect(onClose).toHaveBeenCalledTimes(2)
  })

  it('renders loading and error states', () => {
    const { rerender } = render(<TablePreviewModal preview={null} isLoading error={null} onClose={() => undefined} />)

    expect(screen.getByText('Loading table preview…')).toBeInTheDocument()

    rerender(<TablePreviewModal preview={null} isLoading={false} error="Preview failed" onClose={() => undefined} />)

    expect(screen.getByRole('alert')).toHaveTextContent('Preview failed')
  })

  it('renders an empty rows message', () => {
    render(
      <TablePreviewModal
        preview={{ ...preview, sample_rows: [] }}
        isLoading={false}
        error={null}
        onClose={() => undefined}
      />,
    )

    expect(screen.getByText('No sample rows available.')).toBeInTheDocument()
    expect(screen.queryByRole('table', { name: 'Sample rows' })).not.toBeInTheDocument()
  })
})
