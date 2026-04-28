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

function formatLayerScores(layerScores: Record<string, number> | null): string {
  if (!layerScores) return 'No layer scores'
  return Object.entries(layerScores)
    .map(([layer, score]) => `${layer.toUpperCase()} ${score.toFixed(2)}`)
    .join(' · ')
}

export function ResultWorkspace({ task }: ResultWorkspaceProps) {
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

      <div className="view-index" aria-label="Visible result sections">
        {['Graph', 'Ranking', 'Mappings', 'Raw JSON'].map((view) => (
          <span key={view} className="view-index__item">
            {view}
          </span>
        ))}
      </div>

      <ResultGraph graph={graph} />

      <section className="result-section" aria-labelledby="ranking-title">
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

      <section className="result-section" aria-labelledby="mappings-title">
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

      <JsonViewer data={task} title="Raw JSON" />
    </main>
  )
}
