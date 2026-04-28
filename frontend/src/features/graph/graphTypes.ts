import type { MatchScenario } from '../tasks/taskTypes'

export type GraphNodeKind =
  | 'query_table'
  | 'candidate_table'
  | 'source_table'
  | 'target_table'
  | 'source_column'
  | 'target_column'

export type GraphNodeStatus = 'normal' | 'matched' | 'degraded' | 'failed'

export type GraphMetrics = Record<string, number | string>

export type GraphNode = {
  id: string
  kind: GraphNodeKind
  label: string
  table_id?: string
  column_id?: string
  status?: GraphNodeStatus
  metrics?: GraphMetrics
}

export type GraphEdge = {
  id: string
  kind: 'discovery' | 'mapping'
  source: string
  target: string
  label?: string
  weight?: number
  scenario?: MatchScenario
  explanation?: string
  metrics?: GraphMetrics
}

export type TaskGraph = {
  nodes: GraphNode[]
  edges: GraphEdge[]
}
