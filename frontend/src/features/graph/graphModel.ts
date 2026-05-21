import type { TableSummary, TaskDetail } from '../tasks/taskTypes'
import type { GraphEdge, GraphNode, GraphNodeKind, TaskGraph } from './graphTypes'

function buildTableNameLookup(tables: TableSummary[]): Map<string, string> {
  return new Map(tables.map((table) => [table.table_id, table.table_name]))
}

function tableNode(
  tableId: string,
  kind: Extract<GraphNodeKind, `${string}_table`>,
  tableNames: Map<string, string>,
): GraphNode {
  const label = tableNames.get(tableId) ?? tableId

  return {
    id: `table:${tableId}`,
    kind,
    label,
    meta: label === tableId ? undefined : tableId,
    table_id: tableId,
    status: 'normal',
  }
}

function columnNode(
  columnId: string,
  columnName: string | null | undefined,
  kind: Extract<GraphNodeKind, `${string}_column`>,
  isMatched: boolean,
): GraphNode {
  const label = columnName || columnId

  return {
    id: `column:${columnId}`,
    kind,
    label,
    meta: label === columnId ? undefined : columnId,
    column_id: columnId,
    status: isMatched ? 'matched' : 'normal',
  }
}

export function buildTaskGraph(task: TaskDetail, tables: TableSummary[] = []): TaskGraph {
  const nodes = new Map<string, GraphNode>()
  const edges: GraphEdge[] = []
  const tableNames = buildTableNameLookup(tables)

  if (task.query_table_id) {
    const kind = task.task_type === 'MATCH_ONLY' ? 'source_table' : 'query_table'
    nodes.set(`table:${task.query_table_id}`, tableNode(task.query_table_id, kind, tableNames))
  }

  if (task.target_table_id) {
    nodes.set(`table:${task.target_table_id}`, tableNode(task.target_table_id, 'target_table', tableNames))
  }

  for (const item of task.ranking) {
    nodes.set(
      `table:${item.candidate_table}`,
      tableNode(item.candidate_table, 'candidate_table', tableNames),
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
      columnNode(mapping.src_column_id, mapping.src_column_name, 'source_column', mapping.is_matched),
    )
    nodes.set(
      `column:${mapping.tgt_column_id}`,
      columnNode(mapping.tgt_column_id, mapping.tgt_column_name, 'target_column', mapping.is_matched),
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
