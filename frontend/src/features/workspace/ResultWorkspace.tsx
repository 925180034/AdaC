import { useState } from 'react'
import { EmptyState } from '../../components/EmptyState'
import { JsonViewer } from '../../components/JsonViewer'
import { ScoreBar } from '../../components/ScoreBar'
import { StatusBadge } from '../../components/StatusBadge'
import { buildTaskGraph } from '../graph/graphModel'
import { ResultGraph } from '../graph/ResultGraph'
import type { TaskDetail } from '../tasks/taskTypes'

type ResultWorkspaceProps = {
  task: TaskDetail | null
}

type ResultView = 'graph' | 'ranking' | 'mappings' | 'raw'

const RESULT_VIEWS: Array<{ id: ResultView; label: string }> = [
  { id: 'graph', label: 'Graph' },
  { id: 'ranking', label: 'Ranking' },
  { id: 'mappings', label: 'Mappings' },
  { id: 'raw', label: 'Raw JSON' },
]

function panelId(view: ResultView): string {
  return `result-view-${view}`
}

function tabId(view: ResultView): string {
  return `result-tab-${view}`
}

function formatLayerScores(layerScores: Record<string, number> | null): string {
  if (!layerScores) return 'No layer scores'
  return Object.entries(layerScores)
    .map(([layer, score]) => `${layer.toUpperCase()} ${score.toFixed(2)}`)
    .join(' · ')
}

export function ResultWorkspace({ task }: ResultWorkspaceProps) {
  const [activeView, setActiveView] = useState<ResultView>('graph')

  if (!task) {
    return (
      <main className="panel result-workspace" aria-labelledby="results-title">
        <div className="panel__header">
          <div>
            <p className="panel-kicker">Central workspace</p>
            <h2 id="results-title">Result Workspace</h2>
          </div>
        </div>
        <EmptyState
          title="No active task"
          description="Choose a mode and table context, then run AdaCascade to populate graph, ranking, mappings, and raw JSON views. This preview intentionally does not auto-run."
        />
      </main>
    )
  }

  const graph = buildTaskGraph(task)

  return (
    <main className="panel result-workspace" aria-labelledby="results-title">
      <div className="panel__header result-workspace__header">
        <div>
          <p className="panel-kicker">Central workspace</p>
          <h2 id="results-title">Result Workspace</h2>
          <p className="result-workspace__subtitle">Task {task.task_id}</p>
        </div>
        <StatusBadge status={task.status} />
      </div>

      <div className="view-index" role="tablist" aria-label="Result views">
        {RESULT_VIEWS.map((view) => (
          <button
            key={view.id}
            type="button"
            className="view-index__item"
            role="tab"
            id={tabId(view.id)}
            aria-controls={panelId(view.id)}
            aria-selected={activeView === view.id}
            onClick={() => setActiveView(view.id)}
          >
            {view.label}
          </button>
        ))}
      </div>

      {activeView === 'graph' ? (
        <div id={panelId('graph')} role="tabpanel" aria-labelledby={tabId('graph')}>
          <ResultGraph graph={graph} />
        </div>
      ) : null}

      {activeView === 'ranking' ? (
        <section id={panelId('ranking')} role="tabpanel" className="result-section" aria-label="Ranking results" aria-labelledby={tabId('ranking')}>
          <div className="section-title-row">
            <h3 id="ranking-title">Ranking</h3>
            <span>{task.ranking.length} candidates</span>
          </div>
          <div className="ranking-list">
            {task.ranking.map((row) => (
              <article className="ranking-row" key={`${row.rank}-${row.candidate_table}`}>
                <div className="ranking-row__rank">#{row.rank}</div>
                <div className="ranking-row__body">
                  <h4>{row.candidate_table}</h4>
                  <p>{formatLayerScores(row.layer_scores)}</p>
                </div>
                <ScoreBar value={row.score} label={`Candidate ${row.rank} score`} tone="green" />
              </article>
            ))}
          </div>
        </section>
      ) : null}

      {activeView === 'mappings' ? (
        <section id={panelId('mappings')} role="tabpanel" className="result-section" aria-label="Column mapping results" aria-labelledby={tabId('mappings')}>
          <div className="section-title-row">
            <h3 id="mappings-title">Mappings</h3>
            <span>{task.mappings.length} alignments</span>
          </div>
          <div className="mapping-grid">
            {task.mappings.map((mapping) => (
              <article className="mapping-card" key={mapping.mapping_id}>
                <div className="mapping-card__pair">
                  <span>{mapping.src_column_id}</span>
                  <span aria-hidden="true">→</span>
                  <span>{mapping.tgt_column_id}</span>
                </div>
                <div className="mapping-card__meta">
                  <StatusBadge status={mapping.is_matched ? 'success' : 'failed'} label={mapping.is_matched ? 'Matched' : 'Rejected'} size="sm" />
                  <span>{mapping.scenario}</span>
                </div>
                <ScoreBar value={mapping.confidence} label="Mapping confidence" tone="violet" />
                <p>{mapping.reasoning ?? 'No reasoning supplied.'}</p>
              </article>
            ))}
          </div>
        </section>
      ) : null}

      {activeView === 'raw' ? (
        <div id={panelId('raw')} role="tabpanel" aria-labelledby={tabId('raw')}>
          <JsonViewer data={task} title="Raw JSON" />
        </div>
      ) : null}
    </main>
  )
}
