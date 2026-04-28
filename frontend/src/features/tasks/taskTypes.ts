export type TaskMode = 'discover' | 'match' | 'integrate'

export type TaskType = 'INTEGRATE' | 'DISCOVER_ONLY' | 'MATCH_ONLY'

export type TaskStatus = 'PENDING' | 'RUNNING' | 'SUCCESS' | 'FAILED' | 'DEGRADED'

export type MatchScenario = 'SMD' | 'SSD' | 'SLD'

export type TableSummary = {
  table_id: string
  tenant_id: string
  table_name: string
  row_count: number | null
  col_count: number | null
  status: string
  source_system?: string | null
  uploaded_by?: string | null
  uploaded_at?: string | null
  updated_at?: string | null
}

export type DiscoveryRanking = {
  rank: number
  candidate_table: string
  score: number
  layer_scores: Record<string, number> | null
}

export type ColumnMapping = {
  mapping_id: string
  src_column_id: string
  tgt_column_id: string
  scenario: MatchScenario
  confidence: number
  is_matched: boolean
  reasoning: string | null
  created_at: string
}

export type AgentTraceStep = {
  step_id: number
  agent_name: string
  layer: string | null
  input_size: number | null
  output_size: number | null
  latency_ms: number | null
  llm_tokens: number | null
  recall_loss: number | null
  started_at: string
  finished_at: string | null
}

export type TaskDetail = {
  task_id: string
  tenant_id: string
  task_type: TaskType
  query_table_id: string | null
  target_table_id: string | null
  status: Extract<TaskStatus, 'RUNNING' | 'SUCCESS' | 'FAILED' | 'DEGRADED'>
  submitted_at: string
  finished_at: string | null
  error_message: string | null
  plan_config: Record<string, unknown> | null
  trace: AgentTraceStep[]
  ranking: DiscoveryRanking[]
  mappings: ColumnMapping[]
}

export type TaskEvent = {
  task_id: string
  type:
    | 'task_created'
    | 'agent_started'
    | 'agent_completed'
    | 'agent_degraded'
    | 'agent_failed'
    | 'task_completed'
    | 'heartbeat'
  agent?: 'Planner' | 'Profiling' | 'Retrieval' | 'Matcher'
  layer?: string
  status?: TaskStatus
  task_type?: TaskType
  input_size?: number
  output_size?: number
  latency_ms?: number
  llm_tokens?: number
  message?: string
  reason?: string
  fallback?: string
  error?: string
  timestamp: string
}
