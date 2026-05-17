import { useEffect, useState } from 'react'
import type { TaskMode, TableSummary } from '../tasks/taskTypes'
import type { AdvancedParameters, ExecutionProfile } from './parameters'

export type TenantOption = {
  value: string
  label: string
}

import { StatusBadge } from '../../components/StatusBadge'
import { getWorkspaceCopy } from './i18n'
import type { Language } from './uiPreferences'

export type TaskControlPanelProps = {
  tenantId: string
  tenantOptions: TenantOption[]
  executionProfile: ExecutionProfile
  parameters: AdvancedParameters
  mode: TaskMode
  tables: TableSummary[]
  queryTableId: string
  sourceTableId: string
  targetTableId: string
  isRunning: boolean
  onTenantChange: (tenantId: string) => void
  onExecutionProfileChange: (profile: ExecutionProfile) => void
  onParameterChange: (key: keyof AdvancedParameters, value: number) => void
  onResetParameters: () => void
  onModeChange: (mode: TaskMode) => void
  onQueryTableChange: (tableId: string) => void
  onSourceTableChange: (tableId: string) => void
  onTargetTableChange: (tableId: string) => void
  onRun: () => void
  onCancel: () => void
  language?: Language
}

function tableLabel(table: TableSummary): string {
  const dimensions = [table.row_count, table.col_count]
    .map((value) => (value === null ? '—' : value.toLocaleString()))
    .join(' × ')
  return `${table.table_name} · ${dimensions}`
}

function parameterValue(value: number): string {
  return Number.isInteger(value) ? String(value) : String(value)
}

function parseParameter(value: string): number | null {
  if (value.trim() === '') return null
  const parsed = Number(value)
  return Number.isNaN(parsed) ? null : parsed
}

export function TaskControlPanel({
  tenantId,
  tenantOptions,
  executionProfile,
  parameters,
  mode,
  tables,
  queryTableId,
  sourceTableId,
  targetTableId,
  isRunning,
  onTenantChange,
  onExecutionProfileChange,
  onParameterChange,
  onResetParameters,
  onModeChange,
  onQueryTableChange,
  onSourceTableChange,
  onTargetTableChange,
  onRun,
  onCancel,
  language = 'en',
}: TaskControlPanelProps) {
  const copy = getWorkspaceCopy(language).control
  const [parameterDrafts, setParameterDrafts] = useState<Record<keyof AdvancedParameters, string>>({
    theta_1: parameterValue(parameters.theta_1),
    theta_2: parameterValue(parameters.theta_2),
    theta_3: parameterValue(parameters.theta_3),
    theta_match: parameterValue(parameters.theta_match),
    matcher_top_k: parameterValue(parameters.matcher_top_k),
  })
  const [focusedParameter, setFocusedParameter] = useState<keyof AdvancedParameters | null>(null)
  const [areAdvancedParametersOpen, setAreAdvancedParametersOpen] = useState(false)
  const tableOptions = tables.map((table) => (
    <option key={table.table_id} value={table.table_id}>
      {tableLabel(table)}
    </option>
  ))

  useEffect(() => {
    setParameterDrafts((current) => ({
      theta_1: focusedParameter === 'theta_1' ? current.theta_1 : parameterValue(parameters.theta_1),
      theta_2: focusedParameter === 'theta_2' ? current.theta_2 : parameterValue(parameters.theta_2),
      theta_3: focusedParameter === 'theta_3' ? current.theta_3 : parameterValue(parameters.theta_3),
      theta_match: focusedParameter === 'theta_match' ? current.theta_match : parameterValue(parameters.theta_match),
      matcher_top_k:
        focusedParameter === 'matcher_top_k' ? current.matcher_top_k : parameterValue(parameters.matcher_top_k),
    }))
  }, [focusedParameter, parameters])

  const handleParameterInput = (key: keyof AdvancedParameters, value: string) => {
    setParameterDrafts((current) => ({ ...current, [key]: value }))
    const parsed = parseParameter(value)
    if (parsed !== null) onParameterChange(key, parsed)
  }

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
        <label className="field" htmlFor="tenant-id">
          <span>{copy.tenant}</span>
          <select
            id="tenant-id"
            value={tenantId}
            onChange={(event) => onTenantChange(event.target.value)}
            disabled={isRunning}
          >
            {tenantOptions.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>

        <label className="field" htmlFor="execution-profile">
          <span>{copy.executionProfile}</span>
          <select
            id="execution-profile"
            value={executionProfile}
            onChange={(event) => onExecutionProfileChange(event.target.value as ExecutionProfile)}
            disabled={isRunning}
          >
            <option value="reproducible">{copy.executionProfiles.reproducible}</option>
            <option value="fast">{copy.executionProfiles.fast}</option>
            <option value="joinTuned">{copy.executionProfiles.joinTuned}</option>
          </select>
        </label>

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

      <button
        className="dataset-panel__tools-toggle"
        type="button"
        aria-expanded={areAdvancedParametersOpen}
        onClick={() => setAreAdvancedParametersOpen((current) => !current)}
      >
        {areAdvancedParametersOpen ? copy.hideAdvancedParameters : copy.showAdvancedParameters}
      </button>

      {areAdvancedParametersOpen ? (
        <fieldset className="advanced-parameters">
          <legend>{copy.advancedParameters}</legend>
        <label className="parameter-field" htmlFor="theta-1">
          <span>{copy.l1Threshold}</span>
          <input
            id="theta-1"
            type="text"
            inputMode="decimal"
            value={parameterDrafts.theta_1}
            onFocus={() => setFocusedParameter('theta_1')}
            onBlur={() => setFocusedParameter(null)}
            onChange={(event) => handleParameterInput('theta_1', event.currentTarget.value)}
            disabled={isRunning}
          />
          <input
            aria-hidden="true"
            tabIndex={-1}
            type="range"
            min="0"
            max="1"
            step="0.01"
            value={parameterValue(parameters.theta_1)}
            onChange={(event) => onParameterChange('theta_1', event.currentTarget.valueAsNumber)}
            disabled={isRunning}
          />
        </label>
        <label className="parameter-field" htmlFor="theta-2">
          <span>{copy.l2Threshold}</span>
          <input
            id="theta-2"
            type="text"
            inputMode="decimal"
            value={parameterDrafts.theta_2}
            onFocus={() => setFocusedParameter('theta_2')}
            onBlur={() => setFocusedParameter(null)}
            onChange={(event) => handleParameterInput('theta_2', event.currentTarget.value)}
            disabled={isRunning}
          />
          <input
            aria-hidden="true"
            tabIndex={-1}
            type="range"
            min="0"
            max="1"
            step="0.01"
            value={parameterValue(parameters.theta_2)}
            onChange={(event) => onParameterChange('theta_2', event.currentTarget.valueAsNumber)}
            disabled={isRunning}
          />
        </label>
        <label className="parameter-field" htmlFor="theta-3">
          <span>{copy.l3Threshold}</span>
          <input
            id="theta-3"
            type="text"
            inputMode="decimal"
            value={parameterDrafts.theta_3}
            onFocus={() => setFocusedParameter('theta_3')}
            onBlur={() => setFocusedParameter(null)}
            onChange={(event) => handleParameterInput('theta_3', event.currentTarget.value)}
            disabled={isRunning}
          />
          <input
            aria-hidden="true"
            tabIndex={-1}
            type="range"
            min="0"
            max="1"
            step="0.01"
            value={parameterValue(parameters.theta_3)}
            onChange={(event) => onParameterChange('theta_3', event.currentTarget.valueAsNumber)}
            disabled={isRunning}
          />
        </label>
        <label className="parameter-field" htmlFor="theta-match">
          <span>{copy.matcherThreshold}</span>
          <input
            id="theta-match"
            type="text"
            inputMode="decimal"
            value={parameterDrafts.theta_match}
            onFocus={() => setFocusedParameter('theta_match')}
            onBlur={() => setFocusedParameter(null)}
            onChange={(event) => handleParameterInput('theta_match', event.currentTarget.value)}
            disabled={isRunning}
          />
          <input
            aria-hidden="true"
            tabIndex={-1}
            type="range"
            min="0"
            max="1"
            step="0.01"
            value={parameterValue(parameters.theta_match)}
            onChange={(event) => onParameterChange('theta_match', event.currentTarget.valueAsNumber)}
            disabled={isRunning}
          />
        </label>
        <label className="parameter-field" htmlFor="matcher-top-k">
          <span>{copy.matcherTopK}</span>
          <input
            id="matcher-top-k"
            type="text"
            inputMode="numeric"
            value={parameterDrafts.matcher_top_k}
            onFocus={() => setFocusedParameter('matcher_top_k')}
            onBlur={() => setFocusedParameter(null)}
            onChange={(event) => handleParameterInput('matcher_top_k', event.currentTarget.value)}
            disabled={isRunning}
          />
          <input
            aria-hidden="true"
            tabIndex={-1}
            type="range"
            min="1"
            max="20"
            step="1"
            value={parameterValue(parameters.matcher_top_k)}
            onChange={(event) => onParameterChange('matcher_top_k', event.currentTarget.valueAsNumber)}
            disabled={isRunning}
          />
        </label>
          <button className="parameter-reset" type="button" onClick={onResetParameters} disabled={isRunning}>
            {copy.resetDefaults}
          </button>
        </fieldset>
      ) : null}

      <div className="task-actions">
        <button className="run-button" type="button" onClick={onRun} disabled={isRunning}>
          {isRunning ? copy.running : copy.run}
        </button>
        {isRunning ? (
          <button className="cancel-button" type="button" onClick={onCancel}>
            {copy.cancel}
          </button>
        ) : null}
      </div>

      <p className="control-panel__note">{copy.note}</p>
    </aside>
  )
}
