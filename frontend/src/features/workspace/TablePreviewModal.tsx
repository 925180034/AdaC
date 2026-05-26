import { useEffect, useRef } from 'react'
import type { TablePreviewResponse } from '../../api/tables'
import type { Language } from './uiPreferences'
import { workspaceCopy } from './i18n'

type TablePreviewModalProps = {
  preview: TablePreviewResponse | null
  isLoading: boolean
  error: string | null
  onClose: () => void
  language?: Language
}

type CellValue = TablePreviewResponse['sample_rows'][number][string]

function formatCellValue(value: CellValue, nullValue: string): string {
  if (value === null || value === undefined) {
    return nullValue
  }

  if (Array.isArray(value)) {
    return value.map((entry) => formatCellValue(entry, nullValue)).join(', ')
  }

  if (typeof value === 'object') {
    return JSON.stringify(value)
  }

  return String(value)
}

export function TablePreviewModal({
  preview,
  isLoading,
  error,
  onClose,
  language = 'en',
}: TablePreviewModalProps) {
  const copy = workspaceCopy[language].tablePreview
  const displayError = error ?? copy.loadError
  const closeButtonRef = useRef<HTMLButtonElement>(null)
  const panelRef = useRef<HTMLElement>(null)

  useEffect(() => {
    closeButtonRef.current?.focus()

    function handleKeyDown(event: globalThis.KeyboardEvent) {
      if (event.key === 'Escape') {
        onClose()
        return
      }

      if (event.key !== 'Tab') return
      const focusableElements = panelRef.current?.querySelectorAll<HTMLElement>(
        'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
      )
      if (!focusableElements || focusableElements.length === 0) return

      const firstElement = focusableElements[0]
      const lastElement = focusableElements[focusableElements.length - 1]
      if (event.shiftKey && document.activeElement === firstElement) {
        event.preventDefault()
        lastElement.focus()
      } else if (!event.shiftKey && document.activeElement === lastElement) {
        event.preventDefault()
        firstElement.focus()
      }
    }

    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [onClose])

  return (
    <div className="table-preview-modal" role="presentation">
      <button className="table-preview-modal__backdrop" type="button" aria-hidden="true" tabIndex={-1} onClick={onClose} />
      <section ref={panelRef} className="table-preview-modal__panel" role="dialog" aria-modal="true" aria-label={copy.title}>
        <header className="table-preview-modal__header">
          <div>
            <p className="table-preview-modal__eyebrow">{copy.title}</p>
            <h2>{preview?.table.table_name ?? copy.title}</h2>
          </div>
          <button ref={closeButtonRef} className="table-preview-modal__close" type="button" onClick={onClose} aria-label={copy.close}>
            ×
          </button>
        </header>

        {isLoading ? (
          <div className="table-preview-modal__state">{copy.loading}</div>
        ) : error ? (
          <div className="table-preview-modal__state table-preview-modal__state--error" role="alert">
            {displayError}
          </div>
        ) : preview ? (
          <div className="table-preview-modal__content">
            <dl className="table-preview-modal__metadata" aria-label={`${preview.table.table_name} metadata`}>
              <div className="table-preview-modal__meta-card">
                <dt>{copy.rows(preview.table.row_count)}</dt>
                <dd>{copy.sampleRows}</dd>
              </div>
              <div className="table-preview-modal__meta-card">
                <dt>{copy.columns(preview.table.col_count)}</dt>
                <dd>{preview.columns.join(', ')}</dd>
              </div>
              <div className="table-preview-modal__meta-card">
                <dt>{copy.status}</dt>
                <dd>{preview.table.status}</dd>
              </div>
              {preview.table.dataset_id ? (
                <div className="table-preview-modal__meta-card">
                  <dt>{copy.dataset}</dt>
                  <dd>{preview.table.dataset_id}</dd>
                </div>
              ) : null}
            </dl>

            <section className="table-preview-modal__sample" aria-label={copy.sampleRows}>
              <h3>{copy.sampleRows}</h3>
              {preview.sample_rows.length === 0 ? (
                <p className="table-preview-modal__empty">{copy.noRows}</p>
              ) : (
                <div className="table-preview-modal__table-shell">
                  <div className="table-preview-modal__table-wrap">
                    <table aria-label={copy.sampleRows}>
                      <thead>
                        <tr>
                          {preview.columns.map((column) => (
                            <th key={column} scope="col">
                              {column}
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {preview.sample_rows.map((row, rowIndex) => (
                          <tr key={rowIndex}>
                            {preview.columns.map((column) => {
                              const text = formatCellValue(row[column], copy.nullValue)
                              return (
                                <td key={column} title={text}>
                                  {text}
                                </td>
                              )
                            })}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </section>
          </div>
        ) : null}
      </section>
    </div>
  )
}
