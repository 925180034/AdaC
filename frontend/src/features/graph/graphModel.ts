import type { TaskDetail } from '../tasks/taskTypes'
import type { GraphEdge, GraphNode, GraphNodeKind, TaskGraph } from './graphTypes'

function tableNode(tableId: string, kind: Extract<GraphNodeKind, `${string}_table`>): GraphNode {
  return {
    id: `table:${tableId}`,
    kind,
    label: tableId,
    table_id: tableId,
    status: 'normal',
  }
}

function columnNode(
  columnId: string,
  kind: Extract<GraphNodeKind, `${string}_column`>,
  isMatched: boolean,
): GraphNode {
  return {
    id: `column:${columnId}`,
    kind,
    label: columnId,
    column_id: columnId,
    status: isMatched ? 'matched' : 'normal',
  }
}

export function buildTaskGraph(task: TaskDetail): TaskGraph {
  const nodes = new Map<string, GraphNode>()
  const edges: GraphEdge[] = []

  if (task.query_table_id) {
    const kind = task.task_type === 'MATCH_ONLY' ? 'source_table' : 'query_table'
    nodes.set(`table:${task.query_table_id}`, tableNode(task.query_table_id, kind))
  }

  if (task.target_table_id) {
    nodes.set(`table:${task.target_table_id}`, tableNode(task.target_table_id, 'target_table'))
  }

  for (const item of task.ranking) {
    nodes.set(
      `table:${item.candidate_table}`,
      tableNode(item.candidate_table, 'candidate_table'),
    )

    if (task.query_table_id) {
      edges.push({
        id: `discovery:${task.query_table_id}:${item.candidate_table}`,
        kind: 'discovery',
        source: `table:${task.query_table_id}`,
        target: `table:${item.candidate_table}`,
        label: `#${item.rank} ${item.score.toFixed(3)}`,
        weight: item.score,
        metrics: item.layer_scores ?? undefined,
      })
    }
  }

  for (const mapping of task.mappings) {
    nodes.set(
      `column:${mapping.src_column_id}`,
      columnNode(mapping.src_column_id, 'source_column', mapping.is_matched),
    )
    nodes.set(
      `column:${mapping.tgt_column_id}`,
      columnNode(mapping.tgt_column_id, 'target_column', mapping.is_matched),
    )
    edges.push({
      id: `mapping:${mapping.mapping_id}`,
      kind: 'mapping',
      source: `column:${mapping.src_column_id}`,
      target: `column:${mapping.tgt_column_id}`,
      label: mapping.confidence.toFixed(3),
      weight: mapping.confidence,
      scenario: mapping.scenario,
      explanation: mapping.reasoning ?? undefined,
    })
  }

  return { nodes: [...nodes.values()], edges }
}
