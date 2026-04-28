import { useState } from 'react'
import { EmptyState } from '../../components/EmptyState'
import { JsonViewer } from '../../components/JsonViewer'
import { ScoreBar } from '../../components/ScoreBar'
import { StatusBadge } from '../../components/StatusBadge'
import { buildTaskGraph } from '../graph/graphModel'
import { ResultGraph } from '../graph/ResultGraph'
import type { TaskDetail } from '../tasks/taskTypes'
import { getWorkspaceCopy } from './i18n'
import type { Language } from './uiPreferences'

type ResultWorkspaceProps = {
  task: TaskDetail | null
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

export function ResultWorkspace({ task, language = 'en' }: ResultWorkspaceProps) {
  const [activeView, setActiveView] = useState<ResultView>('graph')
  const copy = getWorkspaceCopy(language).results

  if (!task) {
    return (
      <main className="panel result-workspace" aria-labelledby="results-title">
        <div className="panel__header">
          <div>
            <p className="panel-kicker">{copy.kicker}</p>
            <h2 id="results-title">{copy.title}</h2>
          </div>
        </div>
        <EmptyState
          title={copy.emptyTitle}
          description={copy.emptyDescription}
        />
      </main>
    )
  }

  const graph = buildTaskGraph(task)

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
          <div className="ranking-list">
            {task.ranking.map((row) => (
              <article className="ranking-row" key={`${row.rank}-${row.candidate_table}`}>
                <div className="ranking-row__rank">#{row.rank}</div>
                <div className="ranking-row__body">
                  <h4>{row.candidate_table}</h4>
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
          <div className="mapping-grid">
            {task.mappings.map((mapping) => (
              <article className="mapping-card" key={mapping.mapping_id}>
                <div className="mapping-card__pair">
                  <span>{mapping.src_column_id}</span>
                  <span aria-hidden="true">→</span>
                  <span>{mapping.tgt_column_id}</span>
                </div>
                <div className="mapping-card__meta">
                  <StatusBadge status={mapping.is_matched ? 'success' : 'failed'} label={mapping.is_matched ? copy.matched : copy.rejected} size="sm" />
                  <span>{mapping.scenario}</span>
                </div>
                <ScoreBar value={mapping.confidence} label={copy.mappingConfidence} tone="violet" />
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
    </main>
  )
}
