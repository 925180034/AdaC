import type { TaskMode, TableSummary } from '../tasks/taskTypes'
import { StatusBadge } from '../../components/StatusBadge'
import { getWorkspaceCopy } from './i18n'
import type { Language } from './uiPreferences'

export type TaskControlPanelProps = {
  tenantId: string
  mode: TaskMode
  tables: TableSummary[]
  queryTableId: string
  sourceTableId: string
  targetTableId: string
  isRunning: boolean
  onModeChange: (mode: TaskMode) => void
  onQueryTableChange: (tableId: string) => void
  onSourceTableChange: (tableId: string) => void
  onTargetTableChange: (tableId: string) => void
  onRun: () => void
  language?: Language
}

function tableLabel(table: TableSummary): string {
  const dimensions = [table.row_count, table.col_count]
    .map((value) => (value === null ? '—' : value.toLocaleString()))
    .join(' × ')
  return `${table.table_name} · ${dimensions}`
}

export function TaskControlPanel({
  tenantId,
  mode,
  tables,
  queryTableId,
  sourceTableId,
  targetTableId,
  isRunning,
  onModeChange,
  onQueryTableChange,
  onSourceTableChange,
  onTargetTableChange,
  onRun,
  language = 'en',
}: TaskControlPanelProps) {
  const copy = getWorkspaceCopy(language).control
  const tableOptions = tables.map((table) => (
    <option key={table.table_id} value={table.table_id}>
      {tableLabel(table)}
    </option>
  ))

  return (
    <aside className="panel control-panel" aria-labelledby="task-control-title">
      <div className="panel__header">
        <div>
          <p className="panel-kicker">{copy.kicker}</p>
          <h2 id="task-control-title">{copy.title}</h2>
        </div>
        <StatusBadge status="ready" label={copy.ready} size="sm" />
      </div>

      <dl className="control-panel__meta" aria-label={copy.contextLabel}>
        <div>
          <dt>{copy.tenant}</dt>
          <dd>{tenantId}</dd>
        </div>
        <div>
          <dt>{copy.tables}</dt>
          <dd>{copy.tablesReady(tables.length)}</dd>
        </div>
      </dl>

      <div className="field-stack">
        <label className="field" htmlFor="task-mode">
          <span>{copy.mode}</span>
          <select
            id="task-mode"
            value={mode}
            onChange={(event) => onModeChange(event.target.value as TaskMode)}
            disabled={isRunning}
          >
            <option value="discover">{copy.modes.discover}</option>
            <option value="integrate">{copy.modes.integrate}</option>
            <option value="match">{copy.modes.match}</option>
          </select>
        </label>

        {mode === 'match' ? (
          <>
            <label className="field" htmlFor="source-table">
              <span>{copy.sourceTable}</span>
              <select
                id="source-table"
                value={sourceTableId}
                onChange={(event) => onSourceTableChange(event.target.value)}
                disabled={isRunning}
              >
                {tableOptions}
              </select>
            </label>
            <label className="field" htmlFor="target-table">
              <span>{copy.targetTable}</span>
              <select
                id="target-table"
                value={targetTableId}
                onChange={(event) => onTargetTableChange(event.target.value)}
                disabled={isRunning}
              >
                {tableOptions}
              </select>
            </label>
          </>
        ) : (
          <label className="field" htmlFor="query-table">
            <span>{copy.queryTable}</span>
            <select
              id="query-table"
              value={queryTableId}
              onChange={(event) => onQueryTableChange(event.target.value)}
              disabled={isRunning}
            >
              {tableOptions}
            </select>
          </label>
        )}
      </div>

      <button className="run-button" type="button" onClick={onRun} disabled={isRunning}>
        {isRunning ? copy.running : copy.run}
      </button>

      <p className="control-panel__note">{copy.note}</p>
    </aside>
  )
}
