import type { TaskMode, TableSummary } from '../tasks/taskTypes'
import { StatusBadge } from '../../components/StatusBadge'

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
}: TaskControlPanelProps) {
  const tableOptions = tables.map((table) => (
    <option key={table.table_id} value={table.table_id}>
      {tableLabel(table)}
    </option>
  ))

  return (
    <aside className="panel control-panel" aria-labelledby="task-control-title">
      <div className="panel__header">
        <div>
          <p className="panel-kicker">Launch vector</p>
          <h2 id="task-control-title">Task Control</h2>
        </div>
        <StatusBadge status="ready" label="Ready" size="sm" />
      </div>

      <dl className="control-panel__meta" aria-label="Workspace context">
        <div>
          <dt>Tenant</dt>
          <dd>{tenantId}</dd>
        </div>
        <div>
          <dt>Tables</dt>
          <dd>{tables.length} ready</dd>
        </div>
      </dl>

      <div className="field-stack">
        <label className="field" htmlFor="task-mode">
          <span>Mode</span>
          <select
            id="task-mode"
            value={mode}
            onChange={(event) => onModeChange(event.target.value as TaskMode)}
            disabled={isRunning}
          >
            <option value="discover">Discover</option>
            <option value="integrate">Integrate</option>
            <option value="match">Match</option>
          </select>
        </label>

        {mode === 'match' ? (
          <>
            <label className="field" htmlFor="source-table">
              <span>Source table</span>
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
              <span>Target table</span>
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
            <span>Query table</span>
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
        {isRunning ? 'Running AdaCascade…' : 'Run AdaCascade'}
      </button>

      <p className="control-panel__note">
        Static shell preview. REST submission and SSE reconciliation will attach in the next task.
      </p>
    </aside>
  )
}
