import { useMemo } from 'react'
import ReactFlow, {
  Background,
  Controls,
  MarkerType,
  Position,
  type Edge,
  type Node,
} from 'reactflow'
import 'reactflow/dist/style.css'
import type { GraphEdge, GraphNode, GraphNodeKind, TaskGraph } from './graphTypes'

type ResultGraphProps = {
  graph: TaskGraph
}

type NodeTone = 'cyan' | 'green' | 'violet'

const NODE_WIDTH = 172
const NODE_HEIGHT = 64
const COLUMN_GAP = 250
const ROW_GAP = 104

function getNodeTone(kind: GraphNodeKind): NodeTone {
  if (kind === 'query_table' || kind === 'source_table') return 'cyan'
  if (kind === 'candidate_table' || kind === 'target_table') return 'green'
  return 'violet'
}

function getNodeColumn(kind: GraphNodeKind): number {
  switch (kind) {
    case 'query_table':
    case 'source_table':
    case 'source_column':
      return 0
    case 'candidate_table':
    case 'target_table':
    case 'target_column':
      return 1
    default:
      return 0
  }
}

function getNodeSubtitle(node: GraphNode): string {
  return node.kind.replace(/_/g, ' ')
}

function toReactFlowNodes(nodes: GraphNode[]): Node[] {
  const columnCounts = new Map<number, number>()

  return nodes.map((graphNode) => {
    const column = getNodeColumn(graphNode.kind)
    const row = columnCounts.get(column) ?? 0
    columnCounts.set(column, row + 1)
    const tone = getNodeTone(graphNode.kind)

    return {
      id: graphNode.id,
      type: 'default',
      position: {
        x: column * COLUMN_GAP,
        y: row * ROW_GAP,
      },
      sourcePosition: Position.Right,
      targetPosition: Position.Left,
      data: {
        label: (
          <div className="graph-node__content">
            <span className="graph-node__label">{graphNode.label}</span>
            <span className="graph-node__meta">{getNodeSubtitle(graphNode)}</span>
          </div>
        ),
      },
      className: `graph-node graph-node--${tone}`,
      style: {
        width: NODE_WIDTH,
        minHeight: NODE_HEIGHT,
      },
      ariaLabel: `${graphNode.label} ${getNodeSubtitle(graphNode)}`,
    } satisfies Node
  })
}

function getEdgeTone(edge: GraphEdge): NodeTone {
  return edge.kind === 'mapping' ? 'violet' : 'cyan'
}

function toReactFlowEdges(edges: GraphEdge[]): Edge[] {
  return edges.map((graphEdge) => {
    const tone = getEdgeTone(graphEdge)

    return {
      id: graphEdge.id,
      source: graphEdge.source,
      target: graphEdge.target,
      label: graphEdge.label,
      type: 'smoothstep',
      markerEnd: {
        type: MarkerType.ArrowClosed,
      },
      className: `graph-edge graph-edge--${tone}`,
      animated: graphEdge.kind === 'mapping',
    } satisfies Edge
  })
}

export function ResultGraph({ graph }: ResultGraphProps) {
  const nodes = useMemo(() => toReactFlowNodes(graph.nodes), [graph.nodes])
  const edges = useMemo(() => toReactFlowEdges(graph.edges), [graph.edges])
  const isEmpty = nodes.length === 0

  return (
    <section className="graph-canvas" aria-labelledby="result-graph-title">
      <div className="graph-canvas__header">
        <div>
          <p className="panel-kicker">Graph</p>
          <h3 id="result-graph-title">Result graph</h3>
        </div>
        <span>{nodes.length} nodes · {edges.length} edges</span>
      </div>

      {isEmpty ? (
        <div className="graph-canvas__empty" role="status">
          No graph nodes are available for this task yet.
        </div>
      ) : (
        <div className="graph-canvas__flow" aria-label="Interactive task result graph">
          <ReactFlow
            nodes={nodes}
            edges={edges}
            fitView
            fitViewOptions={{ padding: 0.24 }}
            nodesDraggable={false}
            nodesConnectable={false}
            elementsSelectable={false}
            proOptions={{ hideAttribution: true }}
          >
            <Background color="rgba(141, 218, 255, 0.22)" gap={28} size={1} />
            <Controls showInteractive={false} />
          </ReactFlow>
        </div>
      )}
    </section>
  )
}
