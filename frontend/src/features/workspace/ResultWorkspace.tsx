import { useState } from 'react'
import { EmptyState } from '../../components/EmptyState'
import { JsonViewer } from '../../components/JsonViewer'
import { ScoreBar } from '../../components/ScoreBar'
import { StatusBadge } from '../../components/StatusBadge'
import { buildTaskGraph } from '../graph/graphModel'
import { ResultGraph } from '../graph/ResultGraph'
import type { TableSummary, TaskDetail } from '../tasks/taskTypes'
import { getWorkspaceCopy } from './i18n'
import type { Language } from './uiPreferences'

type ResultWorkspaceProps = {
  task: TaskDetail | null
  tables?: TableSummary[]
  onPreviewTable?: (tableId: string) => void
  language?: Language
}

type ResultView = 'graph' | 'ranking' | 'mappings' | 'raw'

const RESULT_VIEWS: ResultView[] = ['graph', 'ranking', 'mappings', 'raw']

function panelId(view: ResultView): string {
  return `result-view-${view}`
}

function tabId(view: ResultView): string {
  return `result-tab-${view}`
}

function formatLayerScores(layerScores: Record<string, number> | null, emptyLabel: string): string {
  if (!layerScores) return emptyLabel
  return Object.entries(layerScores)
    .map(([layer, score]) => `${layer.toUpperCase()} ${score.toFixed(2)}`)
    .join(' · ')
}

function confidenceTone(confidence: number): 'green' | 'amber' | 'red' {
  if (confidence >= 0.8) return 'green'
  if (confidence >= 0.5) return 'amber'
  return 'red'
}

function rankingEmptyMessage(task: TaskDetail, copy: ReturnType<typeof getWorkspaceCopy>['results']): string {
  return task.task_type === 'MATCH_ONLY' ? copy.matchNoRanking : copy.noRanking
}

function tableNameLookup(tables: TableSummary[]): Map<string, string> {
  return new Map(tables.map((table) => [table.table_id, table.table_name]))
}

function columnLabel(columnName: string | null | undefined, columnId: string): string {
  return columnName || columnId
}

function runtimeSeconds(task: TaskDetail): number | null {
  const submitted = Date.parse(task.submitted_at)
  const finished = task.finished_at ? Date.parse(task.finished_at) : Date.now()
  if (Number.isNaN(submitted) || Number.isNaN(finished)) return null
  return Math.max(0, Math.round((finished - submitted) / 1000))
}

export function ResultWorkspace({ task, tables = [], onPreviewTable, language = 'en' }: ResultWorkspaceProps) {
  const [activeView, setActiveView] = useState<ResultView>('graph')
  const copy = getWorkspaceCopy(language).results
  const tableNames = tableNameLookup(tables)

  if (!task) {
    return (
      <main className="panel result-workspace" aria-labelledby="results-title">
        <div className="panel__header">
          <div>
            <p className="panel-kicker">{copy.kicker}</p>
            <h2 id="results-title">{copy.title}</h2>
          </div>
        </div>
        <section className="result-dashboard-placeholder" aria-label={copy.placeholderLabel}>
          <EmptyState
            title={copy.emptyTitle}
            description={copy.emptyDescription}
          />
        </section>
      </main>
    )
  }

  const graph = buildTaskGraph(task, tables)

  return (
    <main className="panel result-workspace" aria-labelledby="results-title">
      <div className="panel__header result-workspace__header">
        <div>
          <p className="panel-kicker">{copy.kicker}</p>
          <h2 id="results-title">{copy.title}</h2>
          <p className="result-workspace__subtitle">{copy.taskLabel(task.task_id)}</p>
        </div>
        <StatusBadge status={task.status} />
      </div>

      {task.error_message ? (
        <section className="result-error" role="alert" aria-label={copy.errorDetails}>
          <strong>{copy.errorDetails}</strong>
          <p>{task.error_message}</p>
        </section>
      ) : null}

      <section className="result-summary" aria-label={copy.summaryLabel}>
        <article className="result-summary__card">
          <span>{copy.summaryMode}</span>
          <strong>{task.task_type}</strong>
        </article>
        <article className="result-summary__card">
          <span>{copy.summaryRuntime(runtimeSeconds(task))}</span>
          <strong>{task.status}</strong>
        </article>
        <article className="result-summary__card">
          <span>{copy.summaryCandidates(task.ranking.length)}</span>
          <strong>{task.ranking.length}</strong>
        </article>
        <article className="result-summary__card">
          <span>{copy.summaryMappings(task.mappings.length)}</span>
          <strong>{task.mappings.length}</strong>
        </article>
        <article className="result-summary__card">
          <span>{copy.summaryTenant}</span>
          <strong>{task.tenant_id}</strong>
        </article>
      </section>

      <div className="view-index" role="tablist" aria-label={copy.viewsLabel}>
        {RESULT_VIEWS.map((view) => (
          <button
            key={view}
            type="button"
            className="view-index__item"
            role="tab"
            id={tabId(view)}
            aria-controls={panelId(view)}
            aria-selected={activeView === view}
            onClick={() => setActiveView(view)}
          >
            {copy.tabs[view]}
          </button>
        ))}
      </div>

      <div className="result-content-shell">
        {activeView === 'graph' ? (
          <div id={panelId('graph')} role="tabpanel" aria-labelledby={tabId('graph')}>
            <ResultGraph graph={graph} />
          </div>
        ) : null}

        {activeView === 'ranking' ? (
          <section id={panelId('ranking')} role="tabpanel" className="result-section" aria-label={copy.rankingAria} aria-labelledby={tabId('ranking')}>
          <div className="section-title-row">
            <h3 id="ranking-title">{copy.rankingTitle}</h3>
            <span>{copy.candidates(task.ranking.length)}</span>
          </div>
          {task.ranking.length === 0 ? <p className="result-empty-note">{rankingEmptyMessage(task, copy)}</p> : null}
          <div className="ranking-list">
            {task.ranking.map((row) => (
              <article className="ranking-row" key={`${row.rank}-${row.candidate_table}`}>
                <div className="ranking-row__rank">#{row.rank}</div>
                <div className="ranking-row__body">
                  <h4>
                    <button
                      className="table-preview-trigger"
                      type="button"
                      aria-label={`Preview ${tableNames.get(row.candidate_table) ?? row.candidate_table}`}
                      onClick={() => onPreviewTable?.(row.candidate_table)}
                      disabled={!onPreviewTable}
                    >
                      {tableNames.get(row.candidate_table) ?? row.candidate_table}
                    </button>
                  </h4>
                  <p>{formatLayerScores(row.layer_scores, copy.noLayerScores)}</p>
                </div>
                <ScoreBar value={row.score} label={copy.candidateScore(row.rank)} tone="green" />
              </article>
            ))}
          </div>
        </section>
      ) : null}

      {activeView === 'mappings' ? (
        <section id={panelId('mappings')} role="tabpanel" className="result-section" aria-label={copy.mappingsAria} aria-labelledby={tabId('mappings')}>
          <div className="section-title-row">
            <h3 id="mappings-title">{copy.mappingsTitle}</h3>
            <span>{copy.alignments(task.mappings.length)}</span>
          </div>
          <div className="mapping-preview-actions">
            {task.query_table_id ? (
              <button
                className="table-preview-trigger table-preview-trigger--compact"
                type="button"
                onClick={() => {
                  if (task.query_table_id) onPreviewTable?.(task.query_table_id)
                }}
                disabled={!onPreviewTable}
              >
                {copy.previewQueryTable}
              </button>
            ) : null}
            {task.target_table_id ? (
              <button
                className="table-preview-trigger table-preview-trigger--compact"
                type="button"
                onClick={() => {
                  if (task.target_table_id) onPreviewTable?.(task.target_table_id)
                }}
                disabled={!onPreviewTable}
              >
                {copy.previewTargetTable}
              </button>
            ) : null}
          </div>
          <div className="mapping-grid">
            {task.mappings.map((mapping) => (
              <article className="mapping-card" key={mapping.mapping_id}>
                <div className="mapping-card__pair">
                  <span className="mapping-card__column" title={columnLabel(mapping.src_column_name, mapping.src_column_id)}>
                    {columnLabel(mapping.src_column_name, mapping.src_column_id)}
                  </span>
                  <span className="mapping-card__arrow" aria-hidden="true">→</span>
                  <span className="mapping-card__column" title={columnLabel(mapping.tgt_column_name, mapping.tgt_column_id)}>
                    {columnLabel(mapping.tgt_column_name, mapping.tgt_column_id)}
                  </span>
                </div>
                <div className="mapping-card__meta">
                  <StatusBadge status={mapping.is_matched ? 'success' : 'failed'} label={mapping.is_matched ? copy.matched : copy.rejected} size="sm" />
                  <span className={`scenario-badge scenario-badge--${mapping.scenario.toLowerCase()}`}>
                    {copy.scenarioLabel(mapping.scenario)}
                  </span>
                </div>
                <ScoreBar value={mapping.confidence} label={copy.mappingConfidence} tone={confidenceTone(mapping.confidence)} />
                <p>{mapping.reasoning ?? copy.noReasoning}</p>
              </article>
            ))}
          </div>
        </section>
      ) : null}

        {activeView === 'raw' ? (
          <div id={panelId('raw')} role="tabpanel" aria-labelledby={tabId('raw')}>
            <JsonViewer data={task} title={copy.rawTitle} />
          </div>
        ) : null}
      </div>
    </main>
  )
}
